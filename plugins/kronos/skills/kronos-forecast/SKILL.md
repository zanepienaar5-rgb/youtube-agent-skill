---
name: kronos-forecast
description: >-
  Sample possible future price paths for a stock or ETF with Kronos, the
  open-source candlestick foundation model, and backtest whether it has any
  edge on that ticker before anyone leans on it. Works on JSE (.JO), US and
  other Yahoo symbols, and on EasyEquities contract codes (EQU.ZA.STX40).
  Use for "forecast", "where could X go", "Kronos", "predict the price",
  "probability it goes up", or "is this model any good on X".
---

# kronos-forecast

Kronos reads recent candlesticks and samples what the next ones could look like. One sampled line
always looks convincing, which is the danger. This skill always reports the **spread** of many
paths, and it treats a backtest as part of the answer, not an optional extra.

```bash
python3 kronos_forecast.py setup                                 # first time only
python3 kronos_forecast.py backtest STX40.JO --days 10 --folds 20
python3 kronos_forecast.py forecast STX40.JO --days 10 --paths 30
python3 kronos_forecast.py forecast EQU.ZA.NPN --days 5          # EasyEquities code -> NPN.JO
python3 kronos_forecast.py forecast TSLA --interval 5m --days 78 # one session of 5-minute bars
```

The script is in the same folder as this file. Add `--json` to get output you can read and work
with.

## The run

1. **Setup check.** If the script says Kronos or torch is missing, run `setup` and give the user
   the pip line. On a cloud or sandbox machine you may install it yourself. On the user's own
   machine, ask first: torch is a large download.
2. **Backtest first, unless one ran for this ticker, interval and horizon in this conversation.**
   It takes minutes on a CPU (about 5 for 20 folds of 20 paths on daily bars), so tell the user it's
   running. Use `--paths 20` to keep it quick.
3. **Forecast**, with `--paths 30` or more.
4. **Report** (format below).

## What to hand back

```
<TICKER>, next <N> <bars>. Kronos-<size>, <paths> paths, data to <last bar date>

Range:   p10 <x> (<-a%>)   median <y> (<+b%>)   p90 <z> (<+c%>)
Paths ending higher: <n>%

Backtest (<folds> folds): direction <h>% vs <m>% always-majority; error <e>% vs <naive>% no-change;
band caught the real price <cov>% of the time (should be ~80%).
Verdict: <the script's verdict, in one plain sentence>
```

Rules:
- **When the backtest says NO EDGE, the verdict leads**, and the forecast goes underneath as "for
  interest only". That happened on STX40 daily bars (Nov 2026): 50% direction against a 60%
  majority baseline, and worse error than assuming no change.
- **A band that covers under 70% is too narrow.** Say the real range is wider than it looks.
- **Never present the median path as "the prediction"**, and never quote a target price taken from it.
- "Paths ending higher: 80%" is the share of the model's own samples. It is not an 80% chance.
  Compare it with the backtest's Brier score before you call it a probability.
- **No buy or sell advice.** If the user wants to act on it, give the range and the backtest, and
  note that position sizing and stops come from the day-trader pack's `/trader-budget`,
  `/trader-exit` and `/trader-risk`, not from this.
- Yahoo quotes JSE prices in cents. The script converts them to rand so the numbers match
  EasyEquities. Yahoo's JSE data can be a day or two behind, so always show the last bar date.

## With the other skills

- **EasyEquities:** take holdings from `/ee-brief` or `get_holdings`, then run each
  `contract_code` (EQU.ZA.X, EQU.US.X) straight through `forecast`. Run the backtest per ticker,
  because an edge on one ticker says nothing about another.
- **Day trader:** `--interval 5m` gives intraday paths. They don't replace
  `/trader-timemachine`, which replays the ticker's own bars. If the two disagree, report both.

## Limits

- Kronos-small and -base see at most 512 bars back. Kronos-mini sees 2048.
- Earnings, results, halts and news are invisible to it.
- Sampling is random, so two runs differ a little. The backtest is the stable number.
- Not financial advice. This is a research model doing pattern completion on price history.
