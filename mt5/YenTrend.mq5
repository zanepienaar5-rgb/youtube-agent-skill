//+------------------------------------------------------------------+
//| YenTrend.mq5                                                     |
//| Long-only USD/JPY momentum + carry Expert Advisor for MT5.       |
//|                                                                  |
//| The idea, in plain words:                                        |
//|  Holding USD against JPY usually EARNS overnight swap, and when  |
//|  USD/JPY trends, it tends to keep trending. So the bot only      |
//|  BUYS, never sells short, and only while the trend is up.        |
//|                                                                  |
//| Three independent "slices", one per lookback (63, 126 and 252    |
//| trading days, about 3, 6 and 12 months):                         |
//|  - a slice is IN when today's close is above its close N days    |
//|    ago, and OUT when it is not;                                  |
//|  - each slice is one third of the position, so the bot holds     |
//|    0, 1/3, 2/3 or a full position depending on how many agree;   |
//|  - each slice is sized so the whole position moves about the     |
//|    target volatility a year (default 10%);                       |
//|  - each slice has a trailing safety stop at the broker, 6 x ATR  |
//|    below the highest close since entry. After a stop, that slice |
//|    waits for a new 20-day closing high before buying again.     |
//|                                                                  |
//| Tested on USD/JPY daily 2002-2026 with spread and swap: about    |
//| +1.3% a year at 10% volatility, worst drawdown about -22%, and   |
//| positive both before and after 2016. Modest and lumpy: most of   |
//| the gains come in a few strong trend years.                      |
//|                                                                  |
//| Attach to ONE USDJPY chart, D1 timeframe.                        |
//| NOT FINANCIAL ADVICE. Demo first.                                |
//+------------------------------------------------------------------+
#property copyright "MIT licence"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input int    InpLookback1        = 63;   // Slice 1 lookback (days)
input int    InpLookback2        = 126;  // Slice 2 lookback (days)
input int    InpLookback3        = 252;  // Slice 3 lookback (days)
input double InpTargetVolPct     = 10.0; // Target yearly volatility of the full position, %
input int    InpATRPeriod        = 20;   // ATR period (daily)
input double InpStopATR          = 6.0;  // Trailing safety stop, x ATR below highest close (0 = off)
input int    InpReentryHighBars  = 20;   // After a stop: wait for a new N-day closing high
input double InpMaxDailyLossPct  = 3.0;  // No new entries after this % loss today
input double InpMaxSpreadATRPct  = 3.0;  // Max spread as % of ATR (waits out rollover spreads)
input int    InpEntryStartHour   = 2;    // Earliest server hour to enter
input int    InpEntryEndHour     = 22;   // Latest server hour to enter
input long   InpMagic            = 20261200; // Base magic (slices use +1, +2, +3)
input int    InpSlippagePoints   = 30;   // Max slippage, points

CTrade   trade;
int      hATR = INVALID_HANDLE;
int      lookback[3];
datetime lastBar = 0;
bool     wantEntry[3];
string   sliceState[3];
string   g_note = "";

//+------------------------------------------------------------------+
long SliceMagic(int s) { return InpMagic + s + 1; }

string WaitVar(int s)  { return StringFormat("YenTrend_wait_%I64d_%s", SliceMagic(s), _Symbol); }
bool   Waiting(int s)  { return GlobalVariableCheck(WaitVar(s)) && GlobalVariableGet(WaitVar(s)) > 0; }
void   SetWaiting(int s, bool w) { GlobalVariableSet(WaitVar(s), w ? 1.0 : 0.0); }
string HadVar(int s)   { return StringFormat("YenTrend_had_%I64d_%s", SliceMagic(s), _Symbol); }

int OnInit()
{
   lookback[0] = InpLookback1; lookback[1] = InpLookback2; lookback[2] = InpLookback3;
   for(int s = 0; s < 3; s++)
      if(lookback[s] < 5) { Print("YenTrend: lookbacks must be >= 5"); return INIT_PARAMETERS_INCORRECT; }
   if(InpTargetVolPct <= 0) return INIT_PARAMETERS_INCORRECT;
   hATR = iATR(_Symbol, PERIOD_D1, InpATRPeriod);
   if(hATR == INVALID_HANDLE) { Print("YenTrend: could not create ATR"); return INIT_FAILED; }
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   double swapLong = SymbolInfoDouble(_Symbol, SYMBOL_SWAP_LONG);
   if(swapLong < 0)
      g_note = "WARNING: your broker CHARGES swap on USDJPY buys. Part of this strategy's edge is earning it.";
   if(StringFind(_Symbol, "JPY") < 0)
      g_note = g_note + (g_note == "" ? "" : "\n") + "Note: tested on USDJPY only; this chart is " + _Symbol;
   if(Period() != PERIOD_D1) Print("YenTrend: works on daily bars whatever the chart timeframe; D1 chart recommended");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { IndicatorRelease(hATR); Comment(""); }

//+------------------------------------------------------------------+
double ATR1()
{
   double v[];
   if(CopyBuffer(hATR, 0, 1, 1, v) != 1) return 0.0;
   return v[0];
}

ulong SliceTicket(int s)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == SliceMagic(s))
         return t;
   }
   return 0;
}

double Momentum(int s)
{
   double now = iClose(_Symbol, PERIOD_D1, 1);
   double then = iClose(_Symbol, PERIOD_D1, 1 + lookback[s]);
   if(now <= 0 || then <= 0) return 0.0;
   return now / then - 1.0;
}

double DayStartEquity()
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   string name = StringFormat("YenTrend_day_%I64d_%04d%02d%02d", InpMagic, dt.year, dt.mon, dt.day);
   if(!GlobalVariableCheck(name)) GlobalVariableSet(name, AccountInfoDouble(ACCOUNT_EQUITY));
   return GlobalVariableGet(name);
}

bool DailyLimitHit()
{
   double start = DayStartEquity();
   return start > 0 && AccountInfoDouble(ACCOUNT_EQUITY) <= start * (1.0 - InpMaxDailyLossPct / 100.0);
}

// Lots for one slice: the full position should move about TargetVol% a year, so each slice gets a third.
double SliceLots(double atr)
{
   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double dailySigma = atr / 1.25;                      // ATR is roughly 1.25 x the daily standard deviation
   double perLot = 0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, 1.0, price, price - dailySigma, perLot)) return 0.0;
   perLot = MathAbs(perLot);
   if(perLot <= 0) return 0.0;
   double wantDaily = AccountInfoDouble(ACCOUNT_EQUITY) * InpTargetVolPct / 100.0 / MathSqrt(252.0) / 3.0;
   double lots = wantDaily / perLot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double mn   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double mx   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < mn) return 0.0;
   return MathMin(lots, mx);
}

bool EntryConditionsOK(double atr, string &why)
{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   if(dt.hour < InpEntryStartHour || dt.hour > InpEntryEndHour) { why = "waiting: outside entry hours"; return false; }
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(atr <= 0 || spread > atr * InpMaxSpreadATRPct / 100.0) { why = "waiting: spread too wide"; return false; }
   if(DailyLimitHit()) { why = "daily loss limit hit"; return false; }
   return true;
}

// Called every tick: if a slice was open last tick and is gone now, and the bot did not close it
// (its own closes clear the flag first), the broker-side stop was hit, so the slice must wait.
void TrackStops()
{
   for(int s = 0; s < 3; s++)
   {
      ulong t = SliceTicket(s);
      bool had = GlobalVariableCheck(HadVar(s)) && GlobalVariableGet(HadVar(s)) > 0;
      if(t == 0 && had)
      {
         SetWaiting(s, true);
         Print("YenTrend: slice ", lookback[s], "d was stopped out; waiting for a new ", InpReentryHighBars, "-day high");
      }
      GlobalVariableSet(HadVar(s), t != 0 ? 1.0 : 0.0);
   }
}

//+------------------------------------------------------------------+
void OnNewBar()
{
   double atr = ATR1();
   for(int s = 0; s < 3; s++)
   {
      wantEntry[s] = false;
      sliceState[s] = "";
      ulong t = SliceTicket(s);
      double m = Momentum(s);

      if(t != 0)
      {
         if(m <= 0)
         {
            if(trade.PositionClose(t)) { GlobalVariableSet(HadVar(s), 0.0); SetWaiting(s, false); Print("YenTrend: slice ", lookback[s], "d closed, momentum turned down"); }
         }
         else if(InpStopATR > 0 && atr > 0 && PositionSelectByTicket(t))
         {
            int openShift = iBarShift(_Symbol, PERIOD_D1, (datetime)PositionGetInteger(POSITION_TIME), false);
            if(openShift < 1) openShift = 1;
            int hi = iHighest(_Symbol, PERIOD_D1, MODE_CLOSE, openShift, 1);
            double peak = hi >= 0 ? iClose(_Symbol, PERIOD_D1, hi) : iClose(_Symbol, PERIOD_D1, 1);
            double newSL = NormalizeDouble(peak - InpStopATR * atr, _Digits);
            double sl = PositionGetDouble(POSITION_SL);
            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double minGap = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
            if(newSL > sl && newSL < bid - minGap) trade.PositionModify(t, newSL, 0.0);
         }
      }
      else if(m > 0)
      {
         if(Waiting(s))
         {
            int hi = iHighest(_Symbol, PERIOD_D1, MODE_CLOSE, InpReentryHighBars, 2);
            if(hi >= 0 && iClose(_Symbol, PERIOD_D1, 1) > iClose(_Symbol, PERIOD_D1, hi)) { SetWaiting(s, false); wantEntry[s] = true; }
         }
         else wantEntry[s] = true;
      }
      else SetWaiting(s, false);   // momentum down resets the post-stop wait
   }
}

void TryEntries()
{
   double atr = ATR1();
   for(int s = 0; s < 3; s++)
   {
      if(!wantEntry[s]) continue;
      if(SliceTicket(s) != 0) { wantEntry[s] = false; continue; }
      string why = "";
      if(!EntryConditionsOK(atr, why)) { sliceState[s] = why; continue; }
      double lots = SliceLots(atr);
      if(lots <= 0)
      {
         sliceState[s] = "skipped: minimum lot is bigger than the target size (account too small)";
         Print("YenTrend: slice ", lookback[s], "d ", sliceState[s]);
         wantEntry[s] = false; continue;
      }
      double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double sl = (InpStopATR > 0) ? NormalizeDouble(price - InpStopATR * atr, _Digits) : 0.0;
      trade.SetExpertMagicNumber(SliceMagic(s));
      if(trade.Buy(lots, _Symbol, 0, sl, 0, StringFormat("YenTrend %dd", lookback[s]))
         && (trade.ResultRetcode() == TRADE_RETCODE_DONE || trade.ResultRetcode() == TRADE_RETCODE_PLACED))
      {
         Print("YenTrend: slice ", lookback[s], "d BOUGHT ", DoubleToString(lots, 2), " lots, stop ", DoubleToString(sl, _Digits));
         wantEntry[s] = false;
      }
      else sliceState[s] = StringFormat("order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(Bars(_Symbol, PERIOD_D1) < InpLookback3 + InpATRPeriod + 5) { Comment("YenTrend: not enough daily history yet"); return; }
   TrackStops();
   datetime bar = iTime(_Symbol, PERIOD_D1, 0);
   if(bar != lastBar) { lastBar = bar; OnNewBar(); }
   TryEntries();

   string txt = "YenTrend  " + _Symbol + "  (long only)\n";
   int open = 0;
   for(int s = 0; s < 3; s++)
   {
      ulong t = SliceTicket(s);
      if(t != 0) GlobalVariableSet(HadVar(s), 1.0);   // a slice opened this tick counts from now
      string st;
      if(t != 0) { open++; st = "IN"; }
      else if(wantEntry[s]) st = (sliceState[s] != "" ? sliceState[s] : "entering");
      else if(Waiting(s)) st = "OUT, waiting for a new 20-day high after a stop";
      else st = "OUT";
      txt += StringFormat("  %3dd momentum %+.1f%%  %s\n", lookback[s], Momentum(s) * 100.0, st);
   }
   txt += StringFormat("position: %d of 3 slices", open);
   if(g_note != "") txt += "\n" + g_note;
   Comment(txt);
}
//+------------------------------------------------------------------+
