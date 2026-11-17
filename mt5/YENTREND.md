# YenTrend: a USD/JPY bot for MT5

**What it does:** it only **buys** USD/JPY, never sells short, and only while the trend is up.
While it holds, it earns the overnight swap, because US interest rates are higher than Japan's.
It's built from the best thing I found after testing every main strategy family on 25 years of
USD/JPY. **Not financial advice. Demo first.**

## The rules

The bot splits its position into three slices, each watching a different time frame:

| slice | it's IN when today's close is above the close... |
| --- | --- |
| 1 | 63 trading days ago (about 3 months) |
| 2 | 126 trading days ago (about 6 months) |
| 3 | 252 trading days ago (about 1 year) |

- When all three agree, the bot holds a full position. When two agree, two-thirds, and so on.
  When none agree, it holds nothing.
- **Size:** the full position is sized to move about **10% a year**. This setting replaces
  "% risk per trade": a bigger number means bigger swings both ways.
- **Safety stop:** every slice gets a stop at the broker, 6 × ATR below the highest close since it
  bought. It works even if your laptop is off. After a stop, that slice waits for a new 20-day
  high before buying again.
- **It also:** waits out wide spreads around midnight rollover, and stops opening trades after a
  3% loss in a day.

## What testing showed (USD/JPY daily, Nov 2001 to Nov 2026, spread and swap included)

| | before 2016 | 2016 onwards | whole period |
| --- | --- | --- | --- |
| return per unit of risk (Sharpe) | 0.22 | 0.23 | 0.24 |
| average per year, at 10% target volatility | | | **+1.3%** |
| worst drop from a peak | | | **−22%** |
| August 2024 yen crash (with the safety stop) | | | −3.0% (−9.2% without it) |

Read this before you switch it on:
- **The edge is real but small.** It was positive in both halves, which nothing on USD/ZAR managed.
  But +1.3% a year at 10% volatility is not "excellent". Raising the target volatility to 20%
  roughly doubles both the return and the drops.
- **It's lumpy.** Most of the money comes in a few big trend years (2005, 2012–14, 2021–24). In the
  research version, 14 of 24 years were small losses. You need to keep it running through
  boring or losing years for the good years to count.
- **The swap matters.** Part of the edge is earning swap on buys. In MT5, right-click USDJPY →
  Specification → **Swap long** must be positive. If it's negative, the bot shows a warning on the
  chart and the edge shrinks.

## Account size

The smallest trade is usually 0.01 lots ($1 000). Each slice needs at least that, so the minimum
balance for the bot to trade at all (November 2026 prices) is:

| target volatility | minimum balance |
| --- | --- |
| 10% (default) | about **R41 000** |
| 15% | about R27 000 |
| 20% | about R20 000 |

Below that, the bot shows "skipped: minimum lot is bigger than the target size". That's it
protecting you, not a bug.

## Install

Same steps as DailyTrend:
1. In MetaEditor, click **File → New → Expert Advisor (template)**, name it `YenTrend`, paste the
   code over the template, and click **Compile**. It should say 0 errors.
2. Open a **USDJPY** chart and set it to **D1**.
3. Drag **YenTrend** from the Navigator onto it. On the **Common** tab, tick **Allow Algo
   Trading**, then click OK.
4. The top-left of the chart shows each slice's momentum and whether it's IN or OUT.

It can run alongside DailyTrend on gold. They use different magic numbers and won't touch each
other's trades.
