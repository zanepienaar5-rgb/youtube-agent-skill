# DailyTrend: an MT5 trading bot (Expert Advisor)

A trend-following bot that runs on daily candles. You can see every rule, and you can change them
in MT5's settings without touching the code. **Not financial advice. Run it on a demo first.**

## The rules

- **Buy** when yesterday's candle closed above the highest point of the 20 days before it, and the
  trend is up: the 50-day average is above the 200-day average, and price is above the 200-day.
- **Sell** is the mirror image.
- **Stop-loss** is set with every order, at 2 × ATR from the entry. ATR (average true range) is the
  normal daily move, so the stop is wider on wild days and tighter on calm ones.
- **The stop moves up** behind the trade to the lowest low of the last 10 days. It only ever tightens.
- **It exits early** if price closes back through the 200-day average.

## The protection

| setting | default | what it does |
| --- | --- | --- |
| Risk per trade | 1% | sizes each trade so hitting the stop loses about 1% of your equity |
| Max total risk | 3% | caps risk across every chart running the bot, because USD/ZAR, EUR/USD and gold move together |
| Daily loss limit | 3% | no new trades once you are down 3% today |
| Spread filter | 5% of ATR | waits out wide spreads, like USD/ZAR around the midnight rollover |
| Entry hours | 02:00–22:00 server time | keeps out of the rollover |
| News filter | 60 min | no entries within an hour of high-impact news (live only; MT5's tester has no news data) |
| Carry filter | off | if on, only trades the side that *earns* overnight swap |

If the smallest lot your broker allows would risk more than your 1%, **the bot skips the trade
instead of over-risking.** It prints the reason in the Experts tab.

## What the rules did on 20 years of history: read this before you install

I ran the same rules on daily data from Nov 2006 to Nov 2026, with a small spread cost included.
"R" means one unit of risk. At 1% per trade, +10R ≈ +10% of your account, before compounding.

| market | trades | win rate | total | worst drawdown | longest losing run | first 10 yrs / last 10 yrs |
| --- | --- | --- | --- | --- | --- | --- |
| **USD/ZAR** | 66 | 24% | **−19.7R** | −24R | 14 in a row | −10.2R / −9.5R |
| **EUR/USD** | 86 | 28% | **−2.0R** | −13.4R | 10 in a row | +8.7R / −10.3R |
| **Gold** | 108 | 42% | **+21.6R** | −6.6R | 7 in a row | +8.4R / +11.8R |

In plain words:
- **On USD/ZAR these rules lost money in both decades.** The rand makes sharp spikes and then
  reverses, which is the worst case for a breakout bot. **Don't run it on USD/ZAR.**
- **On EUR/USD it went nowhere.** It made money in the first decade and gave it back in the second.
- **On gold it worked in both halves**, with the smallest drawdown. That's the only market here
  where I'd bother with a demo.
- Win rates of 24–42% are normal for trend-following. It loses small and often, and makes its
  money on a few big trends. You need to be able to sit through 7–14 losses in a row.
- This test leaves out overnight swap, which costs money on most gold buy trades, and it uses
  Yahoo prices, not your broker's. **Your own MT5 backtest on your broker's data is the one that
  counts.** The past is not the future.

## How big does the account need to be?

The smallest trade is usually 0.01 lots. With a 2 × ATR stop (November 2026 prices):

| market | loss at the stop on 0.01 lots | account needed for that to be 1% |
| --- | --- | --- |
| USD/ZAR | about R400 | about R40 000 |
| EUR/USD | about R270 | about R27 000 |
| Gold | about R3 300 | **about R330 000** |

On a smaller account the bot simply won't trade gold at 1%. Your options are to raise "Risk per
trade" (each loss then hurts more), to ask your broker whether it offers smaller gold lots, or to
accept that the account isn't big enough yet. **Don't use the high leverage to get around this.**
Leverage changes how much margin a trade ties up, not how much you lose at the stop.

## Install it

1. **Get MT5 from your broker** and log in to a **demo** account.
2. In MT5: **File → Open Data Folder → MQL5 → Experts**. Copy `DailyTrend.mq5` into that folder.
3. Back in MT5, open the **Navigator** panel (Ctrl+N). Right-click **Expert Advisors → Refresh**.
4. Double-click `DailyTrend` to open it in **MetaEditor**, then press **F7 (Compile)**. The
   bottom panel should say `0 errors`. If it shows errors, send me the text exactly as written.
5. Open a chart (for example XAUUSD) and set it to **D1**, daily candles.
6. Drag `DailyTrend` onto the chart. In the window that opens:
   - **Common** tab: tick **Allow Algo Trading**.
   - **Inputs** tab: change settings here if you want. Leave Magic the same on every chart.
7. Press the **Algo Trading** button on the top toolbar so it turns green.
8. You should see a smiling hat icon in the top-right of the chart and a status line top-left,
   such as "no setup today".

## Backtest it first (on your broker's own data)

1. **View → Strategy Tester** (Ctrl+R).
2. Expert: `DailyTrend`. Symbol: XAUUSD (or another). Timeframe: D1.
3. Dates: the last 10 years or more. Modelling: "Every tick based on real ticks", or "1 minute OHLC".
4. Deposit: what you'd actually put in, in ZAR. Press **Start**.
5. Look at the **Backtest** tab: net profit, **maximum drawdown**, and the number of trades. Send
   me a screenshot and I'll read it with you.

## Then

- Run it on demo for **1–3 months** at least. Check that the trades match the rules.
- It only works while MT5 is **open and online**. If your PC sleeps, the bot stops. A VPS (an
  always-on computer in the cloud, often free or about R150–R300 a month through brokers) fixes that.
- Only then consider a small live account. Treat the first month of live trading as part of the test.

## Questions to ask your broker

- Which company is my account with, the South African FSCA one or an offshore one?
- What is the smallest lot on XAUUSD, and what are the swap rates?
- What are typical spreads on USD/ZAR at 00:00 and at 10:00?
