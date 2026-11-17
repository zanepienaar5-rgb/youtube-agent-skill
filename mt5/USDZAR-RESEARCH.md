# USD/ZAR: can a bot make money? Research notes, November 2026

**Short answer: I couldn't find a USD/ZAR strategy with a reliable edge after real costs.** So I
haven't built a USD/ZAR bot and called it "the best". Here's what was tested and why.

## How it was tested

- **Data:** Yahoo Finance USD/ZAR. Daily bars from Dec 2003 to Nov 2026 (5 971 bars) and hourly
  bars from Jan 2024 to Nov 2026 (17 314 bars).
- **Costs:** the spread on every entry and exit, plus the **overnight swap**. The swap is modelled
  from the SA–US interest-rate gap (approximate annual averages) plus a broker markup of 1.5% a year.
  On USD/ZAR the swap is large: holding USD against ZAR costs you the rate gap every night.
- **Honest selection:** settings were chosen on the first part of the data only (2006–2015 for
  daily, the first half for hourly), then judged on the part they had never seen.
- **Sizing:** positions were sized to 10% annual volatility so strategies compare fairly.
  Sharpe ratio = return per unit of risk; above about 0.5 is decent, 0 is nothing.

## Daily results (chosen on 2006–2015, judged on 2016–2026)

| strategy family | best setting on 2006–15 | Sharpe 2016–26 | yearly return 2016–26 | worst drawdown |
| --- | --- | --- | --- | --- |
| Always long USD/ZAR (bet on rand weakening) | – | −0.21 | −3.1% | −39% |
| Always short (earn the carry) | – | −0.01 | −0.7% | −35% |
| Time-series momentum, long/short | 252-day | +0.03 | −0.3% | −29% |
| Momentum, long only | 252-day | −0.05 | −0.7% | −23% |
| 20-day breakout + 200 EMA (the gold bot's rules) | 20-day | −0.76 | −8.3% | −61% |
| EMA trend, long/short | 200 EMA | −0.88 | −10.4% | −69% |
| Carry with trend filter | 200 EMA | −0.61 | −4.7% | −44% |
| Carry + trend + low-volatility filter | 200 EMA | −0.36 | −2.3% | −30% |
| Mean reversion (fade 2.5σ moves) | 20-day, 2.5σ | −0.04 | −0.5% | −29% |
| RSI(2) fade | 5/95 | +0.27 | +1.3% | −10% (but −0.47 on 2006–15) |

**Why nothing works:** over 20 years, the rand weakened against the dollar by roughly the same
amount that the interest-rate gap pays to hold rand. That's what economists call uncovered interest
parity, and USD/ZAR follows it closely. Betting on rand weakness costs you the swap. Earning the swap
costs you the rand's weakening. Then the broker takes a markup on both. Without the markup, pure
carry is about breakeven. With a 1.5–3% markup it loses 3–4% a year.

**Trend-following is worst of all on the rand.** It spikes in a crisis (2008, 2015, 2020) and
then snaps back, so a trend bot buys the top and sells the bottom.

## Hourly mean reversion: the one real hint

Fading hourly moves of more than 2–2.5σ away from the 48–72 hour average had a **gross** edge in
both halves of the hourly data. But:

| hourly rules (72h mean, fade 2.5σ), out-of-sample half (Jun 2025 to Nov 2026) | no spread | spread 0.010 ZAR | spread 0.020 ZAR |
| --- | --- | --- | --- |
| no stop-loss (unlevered return) | +6.7% | +1.9% | −3.0% |
| **with a 3×ATR stop, 5-day time stop and crisis filter** (in R, 1R = one stop) | – | −9.9R | −18.1R |

The same no-stop rules made +19.7% gross and +15.2% at a 0.010 spread in the first half, so the edge
also shrank by about two-thirds out of sample. The no-stop version looks good **until a rand crisis**: in March
2020 USD/ZAR went from 15 to 19 in weeks, and a no-stop fade bot keeps adding into that move. The
stop is not optional. With it, 34–41% of trades get stopped out before the price reverts, and the
edge disappears in the out-of-sample half at every spread tested.

## Conclusion

- No USD/ZAR strategy here survives realistic retail costs **and** a test on data it wasn't tuned on.
- The deciding factors are the **spread** and the **swap markup**, both set by your broker. Check
  USD/ZAR's spread in MT5's Market Watch and its swap in Specification.
- Of everything tested in this repo, **only the daily trend rules on gold** held up in both halves
  (see `README.md`). That bot needs a big account to run at 1% risk.

Not financial advice. This is a backtest on free data with modelled costs. Your broker's real
spreads and swaps decide the real result.
