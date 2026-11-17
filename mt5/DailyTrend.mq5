//+------------------------------------------------------------------+
//| DailyTrend.mq5                                                   |
//| A daily-candle trend-following Expert Advisor for MT5.           |
//|                                                                  |
//| Rules, in plain words:                                           |
//|  BUY  when yesterday closed above the highest high of the 20     |
//|       days before it, AND the 50-day average is above the        |
//|       200-day average, AND price is above the 200-day average.   |
//|  SELL is the mirror image.                                       |
//|  Stop-loss: 2 x ATR(14) from entry, always set with the order.   |
//|  Trailing stop: follows the lowest low (buy) / highest high      |
//|       (sell) of the last 10 days, only ever tightening.          |
//|  Exit early if the close crosses back through the 200-day avg.   |
//|                                                                  |
//| Protection:                                                      |
//|  - risk per trade as % of equity (default 1%)                    |
//|  - cap on total open risk across every chart running this EA     |
//|  - daily loss limit: no new trades once equity is down X% today  |
//|  - waits out wide spreads (e.g. USD/ZAR at the midnight rollover)|
//|  - skips entries near high-impact news (live trading only)       |
//|  - optional carry filter: only trade the side that earns swap    |
//|                                                                  |
//| Attach one copy to each chart (USDZAR, EURUSD, XAUUSD), all on   |
//| the same Magic number so the total-risk cap sees all of them.    |
//|                                                                  |
//| NOT FINANCIAL ADVICE. Backtest, then demo, before real money.    |
//+------------------------------------------------------------------+
#property copyright "MIT licence"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- strategy
input ENUM_TIMEFRAMES InpTF            = PERIOD_D1; // Candle timeframe
input int    InpBreakoutBars           = 20;   // Breakout: highest high / lowest low of N bars
input int    InpFastMA                 = 50;   // Fast EMA (trend filter)
input int    InpSlowMA                 = 200;  // Slow EMA (trend filter)
input int    InpATRPeriod              = 14;   // ATR period
input double InpStopATR                = 2.0;  // Initial stop = this many ATRs
input double InpTakeProfitATR          = 0.0;  // Take profit in ATRs (0 = none, let the trail exit)
input int    InpTrailBars              = 10;   // Trailing stop: lowest low / highest high of N bars
input bool   InpExitOnTrendFlip        = true; // Close if price closes back through the slow EMA
input bool   InpAllowLong              = true; // Allow buys
input bool   InpAllowShort             = true; // Allow sells
//--- risk
input double InpRiskPct                = 1.0;  // Risk per trade, % of equity
input double InpMaxTotalRiskPct        = 3.0;  // Max open risk across all charts, % of equity
input double InpMaxDailyLossPct        = 3.0;  // Stop opening trades after this % daily loss
input bool   InpCloseAllOnDailyLimit   = false;// Also close open trades when the daily limit hits
//--- execution filters
input double InpMaxSpreadATRPct        = 5.0;  // Max spread as % of ATR (waits out rollover spreads)
input int    InpEntryStartHour         = 2;    // Earliest server hour to enter (skip rollover)
input int    InpEntryEndHour           = 22;   // Latest server hour to enter
input bool   InpNewsFilter             = true; // Skip entries near high-impact news (live only)
input int    InpNewsMinutes            = 60;   // Minutes before/after news to stay out
input bool   InpCarryFilter            = false;// Only trade the direction with positive swap
//--- housekeeping
input long   InpMagic                  = 20261117; // Magic number (same on every chart)
input int    InpSlippagePoints         = 30;   // Max slippage in points

CTrade   trade;
int      hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE, hATR = INVALID_HANDLE;
datetime lastBar = 0;
int      pendingSignal = 0;      // +1 buy, -1 sell, 0 none (valid until next bar)
string   g_status = "";

//+------------------------------------------------------------------+
int OnInit()
{
   if(InpSlowMA <= InpFastMA || InpBreakoutBars < 2 || InpTrailBars < 2 || InpStopATR <= 0 || InpRiskPct <= 0)
   {
      Print("DailyTrend: invalid inputs");
      return INIT_PARAMETERS_INCORRECT;
   }
   hFast = iMA(_Symbol, InpTF, InpFastMA, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, InpTF, InpSlowMA, 0, MODE_EMA, PRICE_CLOSE);
   hATR  = iATR(_Symbol, InpTF, InpATRPeriod);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE || hATR == INVALID_HANDLE)
   {
      Print("DailyTrend: could not create indicators");
      return INIT_FAILED;
   }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hFast); IndicatorRelease(hSlow); IndicatorRelease(hATR);
   Comment("");
}

//+------------------------------------------------------------------+
double Buf(int handle, int shift)
{
   double v[];
   if(CopyBuffer(handle, 0, shift, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
}

bool HasPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
      { ticket = t; return true; }
   }
   return false;
}

// Money lost (account currency) if a position of `lots` goes from `from` to `to`.
double LossMoney(string sym, ENUM_ORDER_TYPE type, double lots, double from, double to)
{
   double p = 0.0;
   if(!OrderCalcProfit(type, sym, lots, from, to, p)) return -1.0;
   return p < 0 ? -p : 0.0;
}

// Sum of open risk (entry to stop) across every position with our magic, any symbol.
double OpenRiskMoney()
{
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string sym  = PositionGetString(POSITION_SYMBOL);
      double sl   = PositionGetDouble(POSITION_SL);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double vol  = PositionGetDouble(POSITION_VOLUME);
      ENUM_ORDER_TYPE ot = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(sl <= 0) { total += AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPct / 100.0; continue; } // no SL: count as full
      double r = LossMoney(sym, ot, vol, open, sl);
      if(r > 0) total += r;
   }
   return total;
}

// Equity at the start of today's server day, shared by every chart via a terminal global variable.
double DayStartEquity()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   string name = StringFormat("DailyTrend_%I64d_%04d%02d%02d", InpMagic, dt.year, dt.mon, dt.day);
   if(!GlobalVariableCheck(name)) GlobalVariableSet(name, AccountInfoDouble(ACCOUNT_EQUITY));
   return GlobalVariableGet(name);
}

bool DailyLimitHit()
{
   double start = DayStartEquity();
   return start > 0 && AccountInfoDouble(ACCOUNT_EQUITY) <= start * (1.0 - InpMaxDailyLossPct / 100.0);
}

bool NewsNearby()
{
   if(!InpNewsFilter || MQLInfoInteger(MQL_TESTER)) return false; // calendar is not available in the tester
   string ccys[2];
   ccys[0] = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_BASE);
   ccys[1] = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   datetime now = TimeTradeServer();
   for(int c = 0; c < 2; c++)
   {
      if(ccys[c] == "" || ccys[c] == "XAU" || ccys[c] == "XAG") continue;
      MqlCalendarValue vals[];
      int n = CalendarValueHistory(vals, now - InpNewsMinutes * 60, now + InpNewsMinutes * 60, NULL, ccys[c]);
      for(int i = 0; i < n; i++)
      {
         MqlCalendarEvent ev;
         if(CalendarEventById(vals[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
            return true;
      }
   }
   return false;
}

bool SpreadOK(double atr)
{
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   return atr > 0 && spread <= atr * InpMaxSpreadATRPct / 100.0;
}

bool InEntryHours()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   return dt.hour >= InpEntryStartHour && dt.hour <= InpEntryEndHour;
}

double NormLots(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double mn   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < mn) return 0.0;           // too small to respect the risk limit: do not trade
   return MathMin(lots, mx);
}

//+------------------------------------------------------------------+
int Signal()
{
   double close1 = iClose(_Symbol, InpTF, 1);
   int    hiIdx  = iHighest(_Symbol, InpTF, MODE_HIGH, InpBreakoutBars, 2);
   int    loIdx  = iLowest(_Symbol, InpTF, MODE_LOW, InpBreakoutBars, 2);
   double fast = Buf(hFast, 1), slow = Buf(hSlow, 1);
   if(hiIdx < 0 || loIdx < 0 || fast == EMPTY_VALUE || slow == EMPTY_VALUE || close1 <= 0) return 0;
   double hh = iHigh(_Symbol, InpTF, hiIdx), ll = iLow(_Symbol, InpTF, loIdx);
   if(InpAllowLong  && close1 > hh && fast > slow && close1 > slow) return  1;
   if(InpAllowShort && close1 < ll && fast < slow && close1 < slow) return -1;
   return 0;
}

void ManagePosition(ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return;
   bool   isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double sl    = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double slow  = Buf(hSlow, 1), close1 = iClose(_Symbol, InpTF, 1);

   if(InpExitOnTrendFlip && slow != EMPTY_VALUE && ((isBuy && close1 < slow) || (!isBuy && close1 > slow)))
   {
      if(trade.PositionClose(ticket)) Print("DailyTrend: closed on trend flip ", _Symbol);
      return;
   }
   double stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(isBuy)
   {
      int idx = iLowest(_Symbol, InpTF, MODE_LOW, InpTrailBars, 1);
      if(idx < 0) return;
      double newSL = NormalizeDouble(iLow(_Symbol, InpTF, idx), _Digits);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(newSL > sl && newSL < bid - stopsLevel) trade.PositionModify(ticket, newSL, tp);
   }
   else
   {
      int idx = iHighest(_Symbol, InpTF, MODE_HIGH, InpTrailBars, 1);
      if(idx < 0) return;
      double newSL = NormalizeDouble(iHigh(_Symbol, InpTF, idx), _Digits);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if((sl == 0 || newSL < sl) && newSL > ask + stopsLevel) trade.PositionModify(ticket, newSL, tp);
   }
}

void TryEnter(int dir)
{
   double atr = Buf(hATR, 1);
   if(atr == EMPTY_VALUE || atr <= 0) { g_status = "no ATR yet"; return; }
   if(!InEntryHours())  { g_status = "signal waiting: outside entry hours"; return; }
   if(!SpreadOK(atr))   { g_status = "signal waiting: spread too wide"; return; }
   if(NewsNearby())     { g_status = "signal waiting: high-impact news nearby"; return; }
   if(InpCarryFilter)
   {
      double swap = SymbolInfoDouble(_Symbol, dir > 0 ? SYMBOL_SWAP_LONG : SYMBOL_SWAP_SHORT);
      if(swap < 0) { g_status = "signal skipped: carry filter (negative swap)"; pendingSignal = 0; return; }
   }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskMoney = equity * InpRiskPct / 100.0;
   double room = equity * InpMaxTotalRiskPct / 100.0 - OpenRiskMoney();
   if(room <= 0) { g_status = "signal skipped: total risk cap reached"; pendingSignal = 0; return; }
   riskMoney = MathMin(riskMoney, room);

   ENUM_ORDER_TYPE ot = dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double price  = dir > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slDist = atr * InpStopATR;
   double stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(slDist <= stopsLevel) slDist = stopsLevel + _Point * 10;
   double sl = NormalizeDouble(dir > 0 ? price - slDist : price + slDist, _Digits);
   double tp = 0.0;
   if(InpTakeProfitATR > 0) tp = NormalizeDouble(dir > 0 ? price + atr * InpTakeProfitATR : price - atr * InpTakeProfitATR, _Digits);

   double lossPerLot = LossMoney(_Symbol, ot, 1.0, price, sl);
   if(lossPerLot <= 0) { g_status = "could not price the stop"; return; }
   double lots = NormLots(riskMoney / lossPerLot);
   if(lots <= 0)
   {
      g_status = StringFormat("signal skipped: minimum lot would risk more than %.2f", riskMoney);
      Print("DailyTrend: ", g_status, " on ", _Symbol, ". Account too small for this stop at this risk %.");
      pendingSignal = 0; return;
   }
   bool ok = dir > 0 ? trade.Buy(lots, _Symbol, 0, sl, tp, "DailyTrend")
                     : trade.Sell(lots, _Symbol, 0, sl, tp, "DailyTrend");
   if(ok && (trade.ResultRetcode() == TRADE_RETCODE_DONE || trade.ResultRetcode() == TRADE_RETCODE_PLACED))
   {
      g_status = StringFormat("%s %.2f lots, SL %s, risk about %.2f", dir > 0 ? "BOUGHT" : "SOLD", lots,
                            DoubleToString(sl, _Digits), LossMoney(_Symbol, ot, lots, price, sl));
      Print("DailyTrend: ", g_status, " ", _Symbol);
      pendingSignal = 0;
   }
   else
      g_status = StringFormat("order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(Bars(_Symbol, InpTF) < InpSlowMA + InpBreakoutBars + 5) { Comment("DailyTrend: not enough history yet"); return; }

   ulong ticket = 0;
   bool have = HasPosition(ticket);

   if(DailyLimitHit())
   {
      pendingSignal = 0;
      g_status = "daily loss limit hit: no new trades today";
      if(InpCloseAllOnDailyLimit && have) trade.PositionClose(ticket);
   }

   datetime bar = iTime(_Symbol, InpTF, 0);
   if(bar != lastBar)                         // once per new candle
   {
      lastBar = bar;
      pendingSignal = 0;
      if(have) ManagePosition(ticket);
      else if(!DailyLimitHit())
      {
         pendingSignal = Signal();
         g_status = pendingSignal == 0 ? "no setup today" : (pendingSignal > 0 ? "BUY setup, waiting to enter" : "SELL setup, waiting to enter");
      }
   }
   if(!have && pendingSignal != 0 && !DailyLimitHit()) TryEnter(pendingSignal);

   Comment(StringFormat("DailyTrend  %s\n%s\nopen risk (all charts): %.2f of %.2f cap",
           _Symbol, g_status, OpenRiskMoney(), AccountInfoDouble(ACCOUNT_EQUITY) * InpMaxTotalRiskPct / 100.0));
}
//+------------------------------------------------------------------+
