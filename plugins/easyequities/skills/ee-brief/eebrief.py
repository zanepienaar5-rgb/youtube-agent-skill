#!/usr/bin/env python3
"""eebrief.py - a daily EasyEquities / Satrix brief, built from snapshots.

EasyEquities shows you what you have now. It does not tell you what changed since yesterday, or
how much of that change was the market and how much was you putting money in. This tool keeps one
snapshot a day and works that out.

    python3 eebrief.py fetch                  # log in, pull every account, save today's snapshot
    python3 eebrief.py fetch --session tfsa   # just one configured session
    python3 eebrief.py save collected.json    # save a snapshot Claude assembled from the MCP tools
    python3 eebrief.py brief                  # today vs the previous snapshot
    python3 eebrief.py brief --json
    python3 eebrief.py history --days 30      # value per account across snapshots
    python3 eebrief.py sessions               # which sessions are configured (never prints secrets)

`brief`, `history` and `save` need nothing but Python 3. `fetch` needs the client library:

    pip install easy-equities-client

Config is the same as the easy-equities MCP, so one setup serves both:
    EE_SESSION_<NAME>_USERNAME / _PASSWORD / _PLATFORM (easyequities|satrix)
read from the environment, then $EE_MCP_ENV_FILE, ~/.config/easy-equities-mcp/.env or ./.env.
Cookies are shared with the MCP (~/.easy-equities-mcp/<session>.cookies), so a login on either
side spares the other an OTP challenge.

Snapshots live in ~/.easy-equities-mcp/snapshots/ (override with EE_BRIEF_DIR). Read-only: this
tool never places, changes or cancels an order. The library it uses cannot.
"""
import json, os, re, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
COOKIE_DIR = Path(os.environ.get("EE_MCP_COOKIE_DIR", HOME / ".easy-equities-mcp"))
SNAP_DIR = Path(os.environ.get("EE_BRIEF_DIR", COOKIE_DIR / "snapshots"))
CONCENTRATION = float(os.environ.get("EE_BRIEF_CONCENTRATION", "25"))  # % of one account
TFSA_LIMIT = float(os.environ.get("EE_TFSA_ANNUAL_LIMIT", "36000"))   # check SARS each Budget

# ---------------------------------------------------------------- config (mirrors the MCP)

def _env_files():
    f = [Path(os.environ["EE_MCP_ENV_FILE"])] if os.environ.get("EE_MCP_ENV_FILE") else []
    return f + [HOME / ".config" / "easy-equities-mcp" / ".env", Path.cwd() / ".env"]

def load_config():
    for p in _env_files():
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)  # real env vars win, as in the MCP
            return p
    return None

def sessions():
    out = {}
    for k in os.environ:
        m = re.match(r"^EE_SESSION_(.+?)_USERNAME$", k)
        if m:
            n = m.group(1)
            out[n.lower()] = (os.environ.get(f"EE_SESSION_{n}_USERNAME", ""),
                              os.environ.get(f"EE_SESSION_{n}_PASSWORD", ""),
                              os.environ.get(f"EE_SESSION_{n}_PLATFORM", "easyequities").lower())
    return out

# ---------------------------------------------------------------- money parsing

SYMBOLS = {"R": "ZAR", "$": "USD", "£": "GBP", "€": "EUR", "A$": "AUD"}

def money(s):
    """'R 12 345.67' -> 12345.67, '-$ 1,234.50' -> -1234.5, numbers pass through. None if unparseable."""
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    t = str(s).replace("\xa0", " ").strip()
    neg = t.startswith("-") or t.startswith("(") or "-" in t[:3]
    t = re.sub(r"[^\d.,]", "", t)
    if not t: return None
    if "," in t and "." in t: t = t.replace(",", "")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + "." + tail if len(tail) in (1, 2) else t.replace(",", "")
    try: v = float(t)
    except ValueError: return None
    return -v if neg else v

def currency_of(s, fallback="ZAR"):
    t = str(s or "").strip().lstrip("-( ")
    for sym in sorted(SYMBOLS, key=len, reverse=True):
        if t.startswith(sym): return SYMBOLS[sym]
    return fallback

def _walk(obj, path=""):
    if isinstance(obj, dict):
        if "Label" in obj and "Value" in obj:
            yield str(obj["Label"]), obj["Value"]
        for k, v in obj.items():
            if isinstance(v, (dict, list)): yield from _walk(v, f"{path}.{k}")
            else: yield str(k), v
    elif isinstance(obj, list):
        for v in obj: yield from _walk(v, path)

def from_valuations(val, *needles):
    """First numeric value in the valuations blob whose key/label contains any needle."""
    if isinstance(val, str):
        try: val = json.loads(val)
        except ValueError: return None
    for k, v in _walk(val or {}):
        kl = k.lower().replace(" ", "")
        if any(n in kl for n in needles):
            m = money(v)
            if m is not None: return m
    return None

# ---------------------------------------------------------------- snapshots

def snap_path(d): return SNAP_DIR / f"{d}.json"

def write_snapshot(snap):
    SNAP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    p = snap_path(snap["date"])
    p.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    try: p.chmod(0o600)
    except OSError: pass
    return p

def all_snapshots():
    if not SNAP_DIR.exists(): return []
    return sorted(p for p in SNAP_DIR.glob("*.json") if re.match(r"\d{4}-\d{2}-\d{2}\.json$", p.name))

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def normalise(snap):
    """Accept what the MCP tools return, more or less verbatim, and fill in what is missing."""
    snap.setdefault("date", date.today().isoformat())
    snap.setdefault("taken_at", datetime.now().isoformat(timespec="seconds"))
    for a in snap.get("accounts", []):
        a.setdefault("session", "default")
        a["id"] = str(a.get("id", a.get("name", "?")))
        hs = a.get("holdings") or []
        if isinstance(hs, str): hs = json.loads(hs)
        a["holdings"] = hs
        if not a.get("currency"):
            first = next((h.get("current_value") for h in hs if h.get("current_value")), "")
            a["currency"] = currency_of(first, "USD" if "usd" in a.get("name", "").lower() else "ZAR")
    return snap

# ---------------------------------------------------------------- fetch (live)

def fetch(only=None):
    try:
        import pickle
        from easy_equities_client import constants
        from easy_equities_client.clients import EasyEquitiesClient, SatrixClient
    except ImportError:
        sys.exit("fetch needs the client library:  pip install easy-equities-client\n"
                 "(or use the easy-equities MCP tools and `eebrief.py save`)")
    src = load_config()
    cfg = sessions()
    if only: cfg = {k: v for k, v in cfg.items() if k == only.lower()}
    if not cfg:
        sys.exit("No sessions configured. Put EE_SESSION_<NAME>_USERNAME / _PASSWORD in "
                 "~/.config/easy-equities-mcp/.env (see the ee-brief SKILL.md).")
    snap = {"date": date.today().isoformat(), "taken_at": datetime.now().isoformat(timespec="seconds"),
            "source": "eebrief fetch", "accounts": [], "errors": {}}
    for name, (user, pw, platform) in sorted(cfg.items()):
        c = SatrixClient() if platform == "satrix" else EasyEquitiesClient()
        ck = COOKIE_DIR / f"{name}.cookies"
        ok = False
        if ck.exists():
            try:
                with open(ck, "rb") as fh: c.session.cookies.update(pickle.load(fh))
                r = c.session.get(c._url(constants.PLATFORM_ACCOUNT_OVERVIEW_PATH), allow_redirects=False)
                ok = r.status_code == 200 and "My Investments" in r.text
            except Exception: ok = False
        if not ok:
            if not (user and pw):
                snap["errors"][name] = "no valid cookies and no credentials"; continue
            try:
                c.login(user, pw)
                COOKIE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                with open(ck, "wb") as fh: pickle.dump(c.session.cookies, fh)
                ck.chmod(0o600)
            except Exception as e:
                snap["errors"][name] = (f"login failed: {e}. If EasyEquities wants an OTP, log in once "
                                        "in a browser on this machine to trust it, then retry.")
                continue
        try:
            for acc in c.accounts.list():
                entry = {"session": name, "id": acc.id, "name": acc.name,
                         "trading_currency_id": acc.trading_currency_id}
                try: entry["holdings"] = c.accounts.holdings(acc.id)
                except Exception as e: entry["holdings"] = []; entry["holdings_error"] = str(e)
                try: entry["valuations"] = c.accounts.valuations(acc.id)
                except Exception as e: entry["valuations_error"] = str(e)
                if "tfsa" in acc.name.lower() or "tax free" in acc.name.lower():
                    try: entry["transactions"] = c.accounts.transactions(acc.id)
                    except Exception as e: entry["transactions_error"] = str(e)
                snap["accounts"].append(entry)
        except Exception as e:
            snap["errors"][name] = f"could not list accounts: {e}"
    if not snap["accounts"]:
        for s, e in snap["errors"].items(): print(f"session {s}: {e}", file=sys.stderr)
        sys.exit("Nothing fetched, so no snapshot was written (an existing one is left alone).")
    if not snap["errors"]: del snap["errors"]
    p = write_snapshot(normalise(snap))
    print(f"saved {p}  ({len(snap['accounts'])} accounts"
          + (f", errors: {', '.join(snap['errors'])}" if snap.get("errors") else "") + ")")
    if src: print(f"config: {src}")
    return snap

# ---------------------------------------------------------------- analysis

def holding_rows(acc):
    rows = []
    for h in acc.get("holdings", []):
        rows.append({"name": h.get("name", "?"), "code": h.get("contract_code") or h.get("isin") or h.get("name"),
                     "value": money(h.get("current_value")) or 0.0,
                     "cost": money(h.get("purchase_value")) or 0.0,
                     "price": money(h.get("current_price"))})
    return rows

def acc_key(a): return f"{a.get('session')}:{a.get('id')}"

def tax_year_start(d):
    return date(d.year if d.month >= 3 else d.year - 1, 3, 1)

def tfsa_deposits(acc, today):
    tx = acc.get("transactions") or []
    if isinstance(tx, str):
        try: tx = json.loads(tx)
        except ValueError: return None
    start, total, rows = tax_year_start(today), 0.0, []
    for t in tx:
        text = f"{t.get('Action', '')} {t.get('Comment', '')} {t.get('description', '')}".lower()
        if not re.search(r"deposit|eft|contribution|debit order|transfer in", text): continue
        if re.search(r"fee|withdraw|transfer out|dividend|interest|vat", text): continue
        amt = money(t.get("DebitCredit", t.get("value")))
        raw = str(t.get("TransactionDate", t.get("date", "")))
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw) or re.search(r"/Date\((\d+)", raw)
        if not m or amt is None or amt <= 0: continue
        d = (date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m.lastindex == 3
             else datetime.fromtimestamp(int(m.group(1)) / 1000).date())
        if d >= start: total += amt; rows.append((d.isoformat(), amt, text.strip()[:60]))
    return {"tax_year_from": start.isoformat(), "deposited": round(total, 2), "limit": TFSA_LIMIT,
            "room": round(TFSA_LIMIT - total, 2), "counted": rows}

def analyse(cur, prev):
    pmap = {acc_key(a): a for a in (prev or {}).get("accounts", [])}
    out = {"date": cur["date"], "vs": (prev or {}).get("date"), "accounts": [], "by_currency": {},
           "movers": [], "flags": [], "errors": cur.get("errors", {})}
    for a in cur.get("accounts", []):
        rows, ccy = holding_rows(a), a.get("currency", "ZAR")
        invested = sum(r["value"] for r in rows); cost = sum(r["cost"] for r in rows)
        val = a.get("valuations")
        total = from_valuations(val, "accountvalue", "totalvalue", "portfoliovalue") or invested
        cash = from_valuations(val, "freecash", "cashavailable", "availabletoinvest", "cash")
        pa = pmap.get(acc_key(a))
        prow = {r["code"]: r for r in holding_rows(pa)} if pa else {}
        acc = {"name": a.get("name"), "session": a.get("session"), "currency": ccy, "value": round(total, 2),
               "invested": round(invested, 2), "cost": round(cost, 2), "cash": cash,
               "pl": round(invested - cost, 2), "pl_pct": round((invested / cost - 1) * 100, 2) if cost else None,
               "day_market": None, "day_flow": None, "holdings": []}
        if pa:
            # Market move only counts holdings held on both days, with any change in cost (a top-up
            # or a partial sale) taken out. Everything else in the value change is you: new buys,
            # full sales, top-ups. That is reported as flow, never as performance.
            pinv = sum(r["value"] for r in prow.values())
            both = [(r, prow[r["code"]]) for r in rows if r["code"] in prow]
            mkt = sum((r["value"] - p["value"]) - (r["cost"] - p["cost"]) for r, p in both)
            base = sum(p["value"] for _, p in both)
            acc["day_market"] = round(mkt, 2)
            acc["day_flow"] = round((invested - pinv) - mkt, 2)
            acc["day_market_pct"] = round(mkt / base * 100, 2) if base else None
        for r in sorted(rows, key=lambda r: -r["value"]):
            w = r["value"] / invested * 100 if invested else 0
            h = {"name": r["name"], "code": r["code"], "value": r["value"], "weight": round(w, 1),
                 "pl": round(r["value"] - r["cost"], 2),
                 "pl_pct": round((r["value"] / r["cost"] - 1) * 100, 1) if r["cost"] else None}
            p = prow.get(r["code"])
            if p:
                mv = (r["value"] - p["value"]) - (r["cost"] - p["cost"])
                h["day"] = round(mv, 2); h["day_pct"] = round(mv / p["value"] * 100, 2) if p["value"] else None
                if h["day_pct"] is not None:
                    out["movers"].append({**h, "account": a.get("name"), "currency": ccy})
            elif prev:
                h["new"] = True
            acc["holdings"].append(h)
            if w >= CONCENTRATION and len(rows) > 1:
                out["flags"].append(f"{r['name']} is {w:.0f}% of {a.get('name')}")
        for code in set(prow) - {r["code"] for r in rows}:
            out["flags"].append(f"{prow[code]['name']} is gone from {a.get('name')} since {prev['date']}")
        if a.get("holdings_error"): out["flags"].append(f"{a.get('name')}: holdings not read ({a['holdings_error']})")
        if "transactions" in a:
            acc["tfsa"] = tfsa_deposits(a, date.fromisoformat(cur["date"]))
            t = acc["tfsa"]
            if t and t["room"] < 0:
                out["flags"].append(f"{a.get('name')}: deposits this tax year ({t['deposited']:,.0f}) are over the "
                                    f"{TFSA_LIMIT:,.0f} limit - SARS taxes the excess at 40%. Check this now.")
        c = out["by_currency"].setdefault(ccy, {"value": 0.0, "day_market": 0.0, "have_day": False})
        c["value"] += total
        if acc["day_market"] is not None: c["day_market"] += acc["day_market"]; c["have_day"] = True
        out["accounts"].append(acc)
    for pk in set(pmap) - {acc_key(a) for a in cur.get("accounts", [])}:
        out["flags"].append(f"account {pmap[pk].get('name')} was in {prev['date']} but not today - did a login fail?")
    out["movers"].sort(key=lambda m: -abs(m["day_pct"]))
    return out

# ---------------------------------------------------------------- printing

def fmt(v, ccy="ZAR", sign=False):
    if v is None: return "-"
    sym = {"ZAR": "R", "USD": "$", "GBP": "£", "EUR": "€", "AUD": "A$"}.get(ccy, ccy + " ")
    s = f"{abs(v):,.2f}".replace(",", " ")
    pre = ("+" if v >= 0 else "-") if sign else ("-" if v < 0 else "")
    return f"{pre}{sym}{s}"

def pct(v): return "-" if v is None else f"{v:+.2f}%"

def print_brief(r):
    hdr = f"EASYEQUITIES BRIEF  {r['date']}" + (f"   (vs {r['vs']})" if r["vs"] else "   (first snapshot - no day change yet)")
    print(hdr); print("=" * len(hdr))
    for ccy, c in r["by_currency"].items():
        line = f"{ccy} total  {fmt(c['value'], ccy)}"
        if c["have_day"]: line += f"   market move {fmt(c['day_market'], ccy, True)}"
        print(line)
    print("(currencies are never added together - no FX rate is assumed)\n")
    for a in r["accounts"]:
        ccy = a["currency"]
        print(f"{a['name']}  [{a['session']}]  {fmt(a['value'], ccy)}")
        bits = [f"since purchase {fmt(a['pl'], ccy, True)} ({pct(a['pl_pct'])})"]
        if a["day_market"] is not None:
            bits.append(f"day {fmt(a['day_market'], ccy, True)} ({pct(a.get('day_market_pct'))})")
            if abs(a["day_flow"] or 0) >= 0.01:
                bits.append(f"buys/sells {fmt(a['day_flow'], ccy, True)} of holdings value")
        if a["cash"] is not None: bits.append(f"cash {fmt(a['cash'], ccy)}")
        print("  " + " | ".join(bits))
        for h in a["holdings"][:8]:
            d = f"  day {pct(h['day_pct'])}" if h.get("day_pct") is not None else ("  NEW" if h.get("new") else "")
            print(f"    {h['name'][:34]:<34} {fmt(h['value'], ccy):>14} {h['weight']:>5.1f}%  "
                  f"P/L {pct(h['pl_pct']) if h['pl_pct'] is not None else '-':>8}{d}")
        if len(a["holdings"]) > 8: print(f"    ... and {len(a['holdings']) - 8} more")
        if a.get("tfsa"):
            t = a["tfsa"]
            left = f"{fmt(t['room'])} room left" if t["room"] >= 0 else f"OVER by {fmt(-t['room'])}"
            print(f"  TFSA: {fmt(t['deposited'])} deposited since {t['tax_year_from']}, {left} of the "
                  f"{fmt(t['limit'])} annual limit (estimate from {len(t['counted'])} deposit rows)")
        print()
    if r["movers"]:
        print("BIGGEST MOVES (market only, your buys and sells taken out)")
        for m in r["movers"][:5]:
            print(f"  {m['name'][:34]:<34} {pct(m['day_pct']):>8}  {fmt(m['day'], m['currency'], True)}  ({m['account']})")
        print()
    if r["flags"] or r["errors"]:
        print("LOOK AT")
        for f in r["flags"]: print(f"  - {f}")
        for s, e in r["errors"].items(): print(f"  - session {s}: {e}")

def history(days):
    snaps = all_snapshots()[-days:]
    if not snaps: sys.exit(f"No snapshots in {SNAP_DIR}. Run `eebrief.py fetch` first.")
    print(f"{'date':<12}" + "account values")
    for p in snaps:
        s = analyse(normalise(load(p)), None)
        print(f"{s['date']:<12}" + "  ".join(f"{a['name'][:18]} {fmt(a['value'], a['currency'])}" for a in s["accounts"]))

# ---------------------------------------------------------------- main

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"): print(__doc__); return
    cmd, rest = a[0], a[1:]
    as_json = "--json" in rest
    opt = lambda f: rest[rest.index(f) + 1] if f in rest and rest.index(f) + 1 < len(rest) else None
    if cmd == "sessions":
        load_config()
        for n, (u, p, pl) in sorted(sessions().items()):
            print(f"{n:<16} {pl:<13} user {'set' if u else 'MISSING'}  password {'set' if p else 'MISSING'}  "
                  f"cookies {'yes' if (COOKIE_DIR / f'{n}.cookies').exists() else 'no'}")
        if not sessions(): print("none configured")
    elif cmd == "fetch":
        fetch(opt("--session"))
    elif cmd == "save":
        if not rest or not Path(rest[0]).exists(): sys.exit("usage: eebrief.py save collected.json")
        snap = load(rest[0])
        if isinstance(snap, list): snap = {"accounts": snap}
        print(f"saved {write_snapshot(normalise(snap))}")
    elif cmd == "brief":
        snaps = all_snapshots()
        want = opt("--date")
        if want: snaps = [p for p in snaps if p.stem <= want]
        if not snaps: sys.exit(f"No snapshots in {SNAP_DIR}. Run `eebrief.py fetch` (or save one) first.")
        cur = normalise(load(snaps[-1])); prev = normalise(load(snaps[-2])) if len(snaps) > 1 else None
        r = analyse(cur, prev)
        if as_json: print(json.dumps(r, indent=2, default=str))
        else: print_brief(r)
    elif cmd == "history":
        history(int(opt("--days") or 30))
    else:
        print(__doc__); sys.exit(1)

if __name__ == "__main__":
    main()
