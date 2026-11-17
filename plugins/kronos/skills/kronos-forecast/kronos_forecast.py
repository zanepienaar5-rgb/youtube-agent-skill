#!/usr/bin/env python3
"""kronos_forecast.py - probabilistic price paths from Kronos, and a backtest that says whether to care.

Kronos (github.com/shiyu-coder/Kronos, AAAI 2026) is a model pre-trained on candlesticks from 45+
exchanges. Give it recent OHLCV bars and it samples what the next bars could look like. This tool
samples many paths and reports their spread, rather than one line that looks more certain than it
is, and it can backtest the same setup on the ticker's own history first.

    python3 kronos_forecast.py setup                           # clone Kronos, print the pip line
    python3 kronos_forecast.py forecast STX40.JO --days 10     # JSE: Yahoo symbol ends in .JO
    python3 kronos_forecast.py forecast EQU.ZA.STX40           # an EasyEquities contract code works too
    python3 kronos_forecast.py forecast AAPL --interval 5m --days 78   # 78 five-minute bars, about a session
    python3 kronos_forecast.py backtest STX40.JO --days 10 --folds 20
    add --json to either for machine-readable output, --model mini|small|base, --paths N

Needs: Python 3.10+, `pip install torch numpy pandas einops huggingface_hub safetensors tqdm`, and
the Kronos repo (`setup` clones it to ~/.cache/kronos-skill/Kronos, or set KRONOS_HOME). Weights
download from Hugging Face on first use: mini 4M params, small 25M, base 102M. CPU is fine for
daily bars.

Prices come from Yahoo Finance's public chart endpoint (unofficial, can lag or rate-limit).

NOT FINANCIAL ADVICE. A sampled path is not a prediction you can trade on by itself. Run backtest.
"""
import json, os, subprocess, sys, urllib.request
from pathlib import Path

KRONOS_HOME = Path(os.environ.get("KRONOS_HOME", Path.home() / ".cache" / "kronos-skill" / "Kronos"))
MODELS = {"mini": ("NeoQuasar/Kronos-mini", "NeoQuasar/Kronos-Tokenizer-2k", 2048),
          "small": ("NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base", 512),
          "base": ("NeoQuasar/Kronos-base", "NeoQuasar/Kronos-Tokenizer-base", 512)}
RANGE_FOR = {"1d": "5y", "1wk": "10y", "1h": "730d", "30m": "60d", "15m": "60d", "5m": "60d", "1m": "7d"}

# ---------------------------------------------------------------- symbols and data

def yahoo_symbol(s):
    """EQU.ZA.STX40 -> STX40.JO, EQU.US.AAPL -> AAPL, anything else unchanged."""
    p = s.strip().upper().split(".")
    if len(p) == 3 and p[0] == "EQU":
        return p[2] + ".JO" if p[1] == "ZA" else p[2]
    return s.strip().upper()

def fetch_bars(symbol, interval="1d"):
    import pandas as pd
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={RANGE_FOR.get(interval, '2y')}&interval={interval}&includePrePost=false")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kronos-forecast)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    res = (data.get("chart") or {}).get("result")
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        sys.exit(f"No data for {symbol}: {err.get('description', 'unknown symbol?')}. JSE tickers end in .JO")
    res = res[0]; q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"timestamps": pd.to_datetime(res["timestamp"], unit="s"),
                       "open": q["open"], "high": q["high"], "low": q["low"],
                       "close": q["close"], "volume": q["volume"]}).dropna()
    df = df[df["close"] > 0].reset_index(drop=True)
    df["volume"] = df["volume"].astype(float)
    df["amount"] = df["volume"] * df["close"]
    meta = res.get("meta", {})
    # Yahoo quotes JSE stocks in cents (ZAc). Report rand so it matches EasyEquities.
    scale = 0.01 if meta.get("currency") == "ZAc" else 1.0
    if scale != 1.0:
        for c in ("open", "high", "low", "close"): df[c] = df[c] * scale
        df["amount"] = df["volume"] * df["close"]
    ccy = "ZAR" if meta.get("currency") in ("ZAc", "ZAR") else meta.get("currency", "?")
    return df, ccy

def future_stamps(df, n, interval):
    import pandas as pd
    last = df["timestamps"].iloc[-1]
    if interval == "1d": return pd.Series(pd.bdate_range(last + pd.Timedelta(days=1), periods=n))
    if interval == "1wk": return pd.Series(pd.date_range(last + pd.Timedelta(weeks=1), periods=n, freq="7D"))
    step = df["timestamps"].diff().dropna().mode().iloc[0]
    return pd.Series([last + step * (i + 1) for i in range(n)])

# ---------------------------------------------------------------- model

def load_predictor(size):
    if not (KRONOS_HOME / "model" / "kronos.py").exists():
        sys.exit(f"Kronos not found at {KRONOS_HOME}. Run: python3 {Path(__file__).name} setup")
    sys.path.insert(0, str(KRONOS_HOME))
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor
    except ImportError as e:
        sys.exit(f"Kronos needs its Python packages ({e}). Run:\n  pip install torch numpy pandas "
                 "einops huggingface_hub safetensors tqdm")
    mid, tid, ctx = MODELS[size]
    tok = KronosTokenizer.from_pretrained(tid); mdl = Kronos.from_pretrained(mid)
    return KronosPredictor(mdl, tok, max_context=ctx), ctx

def sample_paths(pred, x_df, x_ts, y_ts, n_days, n_paths, T=1.0, top_p=0.9):
    """n_paths independent sampled paths -> array [n_paths, n_days] of closes (plus highs/lows)."""
    import numpy as np
    cols = ["open", "high", "low", "close", "volume", "amount"]
    outs = pred.predict_batch(df_list=[x_df[cols].reset_index(drop=True)] * n_paths,
                              x_timestamp_list=[x_ts.reset_index(drop=True)] * n_paths,
                              y_timestamp_list=[y_ts.reset_index(drop=True)] * n_paths,
                              pred_len=n_days, T=T, top_p=top_p, sample_count=1, verbose=False)
    return (np.array([o["close"].values for o in outs]),
            np.array([o["high"].values for o in outs]), np.array([o["low"].values for o in outs]))

# ---------------------------------------------------------------- commands

def cmd_setup():
    if (KRONOS_HOME / "model" / "kronos.py").exists():
        print(f"Kronos already at {KRONOS_HOME}")
    else:
        KRONOS_HOME.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/shiyu-coder/Kronos.git",
                        str(KRONOS_HOME)], check=True)
    print("Now install the packages (CPU torch is enough):\n"
          "  pip install torch numpy pandas einops huggingface_hub safetensors tqdm")

def cmd_forecast(sym, days, paths, size, interval, lookback, as_json):
    import numpy as np
    symbol = yahoo_symbol(sym)
    df, ccy = fetch_bars(symbol, interval)
    pred, ctx = load_predictor(size)
    lb = min(lookback or ctx, ctx, len(df))
    if lb < 60: sys.exit(f"Only {len(df)} bars for {symbol}; need at least 60.")
    x = df.iloc[-lb:]; y_ts = future_stamps(df, days, interval)
    closes, highs, lows = sample_paths(pred, x, x["timestamps"], y_ts, days, paths)
    last = float(df["close"].iloc[-1]); end = closes[:, -1]
    q = lambda a, p: float(np.percentile(a, p))
    out = {"symbol": symbol, "currency": ccy, "interval": interval, "model": f"Kronos-{size}",
           "lookback_bars": lb, "paths": paths, "last_bar": str(df["timestamps"].iloc[-1]),
           "last_close": round(last, 4),
           "end": {"p10": round(q(end, 10), 4), "median": round(q(end, 50), 4), "p90": round(q(end, 90), 4)},
           "end_change_pct": {k: round((v / last - 1) * 100, 2) for k, v in
                              {"p10": q(end, 10), "median": q(end, 50), "p90": q(end, 90)}.items()},
           "share_of_paths_up": round(float((end > last).mean()), 3),
           "share_touching_plus5": round(float((highs.max(axis=1) >= last * 1.05).mean()), 3),
           "share_touching_minus5": round(float((lows.min(axis=1) <= last * 0.95).mean()), 3),
           "by_step": [{"t": str(t), "p10": round(q(closes[:, i], 10), 4), "median": round(q(closes[:, i], 50), 4),
                        "p90": round(q(closes[:, i], 90), 4)} for i, t in enumerate(y_ts)]}
    if as_json: print(json.dumps(out, indent=2)); return
    print(f"KRONOS  {symbol}  {interval} bars, {lb} back, {days} ahead, {paths} sampled paths ({out['model']})")
    print(f"last close {last:,.2f} {ccy}  ({out['last_bar']})")
    e, c = out["end"], out["end_change_pct"]
    print(f"in {days} bars:  p10 {e['p10']:,.2f} ({c['p10']:+.1f}%)   median {e['median']:,.2f} ({c['median']:+.1f}%)"
          f"   p90 {e['p90']:,.2f} ({c['p90']:+.1f}%)")
    print(f"paths ending higher: {out['share_of_paths_up']:.0%}   touched +5%: {out['share_touching_plus5']:.0%}"
          f"   touched -5%: {out['share_touching_minus5']:.0%}")
    for s in out["by_step"][:: max(1, days // 10)]:
        print(f"  {s['t'][:16]:<16}  {s['p10']:>10,.2f}  {s['median']:>10,.2f}  {s['p90']:>10,.2f}")
    print("Sampled, not predicted. Run `backtest` on this ticker before you give it any weight.")

def cmd_backtest(sym, days, paths, size, interval, folds, lookback, as_json):
    import numpy as np
    symbol = yahoo_symbol(sym)
    df, ccy = fetch_bars(symbol, interval)
    pred, ctx = load_predictor(size)
    lb = min(lookback or ctx, ctx)
    need = lb + days * folds
    if len(df) < lb + days * 2: sys.exit(f"Only {len(df)} bars; need about {need} for {folds} folds.")
    folds = min(folds, (len(df) - lb) // days)
    rows = []
    for k in range(folds, 0, -1):
        cut = len(df) - k * days            # forecast origin; the next `days` bars are the truth
        x = df.iloc[cut - lb:cut]; truth = df.iloc[cut:cut + days]
        closes, _, _ = sample_paths(pred, x, x["timestamps"], truth["timestamps"], days, paths)
        last = float(x["close"].iloc[-1]); real = float(truth["close"].iloc[-1])
        med = float(np.median(closes[:, -1])); up = float((closes[:, -1] > last).mean())
        lo, hi = np.percentile(closes[:, -1], [10, 90])
        rows.append({"origin": str(x["timestamps"].iloc[-1])[:10], "last": last, "real": real, "median": med,
                     "p_up": up, "dir_hit": (med > last) == (real > last), "in_band": lo <= real <= hi,
                     "err": abs(med - real) / last, "naive_err": abs(last - real) / last})
    n = len(rows)
    hit = sum(r["dir_hit"] for r in rows) / n
    base_up = sum(r["real"] > r["last"] for r in rows) / n
    mae = sum(r["err"] for r in rows) / n * 100; naive = sum(r["naive_err"] for r in rows) / n * 100
    band = sum(r["in_band"] for r in rows) / n
    # Brier score of the "share of paths up" as a probability, vs always guessing the base rate.
    brier = sum((r["p_up"] - (r["real"] > r["last"])) ** 2 for r in rows) / n
    brier0 = sum((base_up - (r["real"] > r["last"])) ** 2 for r in rows) / n
    verdict = ("NO EDGE: the median does no better than 'price stays where it is'" if mae >= naive * 0.98 else
               "SOME SIGNAL on error, small sample, treat with caution")
    if hit <= max(base_up, 1 - base_up): verdict += "; direction no better than always guessing the majority"
    out = {"symbol": symbol, "interval": interval, "horizon": days, "folds": n, "paths": paths,
           "direction_hit_rate": round(hit, 3), "majority_baseline": round(max(base_up, 1 - base_up), 3),
           "median_abs_err_pct": round(mae, 2), "naive_abs_err_pct": round(naive, 2),
           "p10_p90_coverage": round(band, 3), "brier": round(brier, 4), "brier_baseline": round(brier0, 4),
           "verdict": verdict, "folds_detail": rows}
    if as_json: print(json.dumps(out, indent=2, default=str)); return
    print(f"KRONOS BACKTEST  {symbol}  {n} non-overlapping folds of {days} {interval} bars, {paths} paths each")
    print(f"direction right      {hit:.0%}   (always guessing the majority: {max(base_up, 1 - base_up):.0%})")
    print(f"median error         {mae:.2f}%  (naive 'no change': {naive:.2f}%)")
    print(f"real price in p10-p90 band {band:.0%}  (a calibrated band would be about 80%)")
    print(f"Brier on P(up)       {brier:.3f}  (base-rate guess: {brier0:.3f}, lower is better)")
    print(f"verdict: {verdict}")
    if n < 30: print(f"{n} folds is a small sample. One lucky stretch can make or break these numbers.")

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"): print(__doc__); return
    cmd = a[0]
    opt = lambda f, d=None: a[a.index(f) + 1] if f in a and a.index(f) + 1 < len(a) else d
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and not a[i - 1].startswith("--")]
    size = opt("--model", "small")
    if size not in MODELS: sys.exit(f"--model must be one of {', '.join(MODELS)}")
    kw = dict(days=int(opt("--days", 10)), paths=int(opt("--paths", 30)), size=size,
              interval=opt("--interval", "1d"), lookback=int(opt("--lookback", 0)) or None, as_json="--json" in a)
    if cmd == "setup": cmd_setup()
    elif cmd in ("forecast", "backtest") and pos:
        if cmd == "forecast": cmd_forecast(pos[0], **kw)
        else: cmd_backtest(pos[0], folds=int(opt("--folds", 20)), **kw)
    else: print(__doc__); sys.exit(1)

if __name__ == "__main__":
    main()
