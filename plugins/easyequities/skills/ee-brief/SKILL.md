---
name: ee-brief
description: >-
  The daily EasyEquities / Satrix brief: what every account is worth, what the
  market did to it since the last snapshot (with your own buys and sells taken
  out), the biggest movers, concentration, and TFSA room left this tax year.
  Use for "morning brief", "how's my portfolio", "how did my shares do today",
  "EasyEquities update", "check my TFSA", or /ee-brief.
---

# ee-brief

EasyEquities tells you what you hold. It does not tell you what changed overnight, or how much of
that change was the market and how much was you. This skill keeps one snapshot a day and works it
out.

```bash
python3 eebrief.py fetch      # log in, pull every account, save today's snapshot
python3 eebrief.py brief      # today vs the previous snapshot
python3 eebrief.py history --days 30
python3 eebrief.py sessions   # what is configured (never prints secrets)
```

`eebrief.py` is in the same folder as this file. `brief`, `history`, `save` and `sessions` need only
Python 3. `fetch` needs `pip install easy-equities-client`.

## The run

1. **Get today's data.** Try these in order and stop at the first that works:
   - `python3 eebrief.py fetch`. This is the normal path.
   - If `fetch` can't import the library, or the user is in a client with the `easy-equities` MCP
     tools: call `list_sessions`, then `list_accounts` for each session, then `get_holdings` and
     `get_valuations` for each account. For accounts whose name has TFSA or "Tax Free" in it, also
     call `get_transactions`. Write it all to a file shaped like this, pasting the tool outputs in as
     they are, then run `python3 eebrief.py save that-file.json`:
     ```json
     {"accounts": [{"session": "personal", "id": "123", "name": "EasyEquities ZAR",
                    "holdings": [...], "valuations": {...}, "transactions": [...]}]}
     ```
   - If a session fails with an expired login, call the MCP's `refresh_session(name)` once, then
     try again. If it still fails, see **OTP** below. Don't loop.
2. **`python3 eebrief.py brief --json`**, then read it. Don't just paste the text report back.
3. **Write the brief** (format below).

If there is only one snapshot, there is no day change yet. Say that once and give the rest.

## What to hand back

Short. It gets read on a phone before work.

```
<one line: the headline, e.g. "Up R1 240 overnight, nearly all of it Satrix 40.">

ZAR  R  xxx xxx   day +R x xxx (+0.8%)
USD  $   x xxx    day -$ xx    (-0.4%)

Movers: <top 3, name and % each>
Look at: <only the flags that matter today, max 3>
TFSA: R xx xxx room left this tax year     <only if a TFSA exists>
```

Rules:
- **Never add ZAR and USD together**, and never convert between them without a rate the user gave
  you. They are two lines.
- **Market move and money in are different things.** The tool splits them. A day where the value
  went up R5 000 because the user deposited R5 000 is a flat day, so say it that way.
- **Flags are filtered, not dumped.** Concentration that was there yesterday too is not news. A
  holding that vanished, an account missing from today's fetch, a TFSA over its limit: those are.
- **A TFSA over its limit leads the brief**, whatever else happened. SARS taxes excess
  contributions at 40%. The deposit count is an estimate from transaction text, so say it is an
  estimate and tell them to check the EasyEquities TFSA contribution tracker. The limit defaults to
  R36 000 a year (tax year starts 1 March). If the Budget changed it, set `EE_TFSA_ANNUAL_LIMIT`.
- No buy or sell advice. No price targets. No "you should rebalance". If the user asks what to do,
  give the facts that bear on it (weight, cost, P/L, concentration) and leave the decision with them.

## Make it daily

Snapshots only build up if something takes them. Two ways, and the first is better because it
works even on days the user doesn't open Claude:

- **The OS does the fetch.** Weekdays after the JSE closes (17:00 SAST), e.g. in `crontab -e`:
  `15 18 * * 1-5 python3 /path/to/eebrief.py fetch >> ~/.easy-equities-mcp/fetch.log 2>&1`
  Then `/ee-brief` in the morning only has to run `brief`.
- **Claude does it.** `/loop 1d /ee-brief`, or a scheduled task if this client has them.

Fetching once a day is plenty. More often just risks EasyEquities flagging the login.

## Setup (first run only)

Run `python3 eebrief.py sessions`. If nothing is configured, take the user through it:

1. Create `~/.config/easy-equities-mcp/.env` with `chmod 600`:
   ```
   EE_SESSION_PERSONAL_USERNAME=their-login
   EE_SESSION_PERSONAL_PASSWORD=their-password
   EE_SESSION_PERSONAL_PLATFORM=easyequities
   ```
   Add another block per login (`EE_SESSION_SATRIX_...` with `PLATFORM=satrix`). One login covers
   every account under it (ZAR, USD, TFSA, RA), so most people need one block.
2. **Never ask for the password in chat, and never write it yourself.** Tell the user to open the
   file and type it in. Then run `sessions` to confirm it says `set`.
3. `pip install easy-equities-client`, then `python3 eebrief.py fetch`.

## OTP

The library logs in with a plain form post and can't answer an OTP. EasyEquities usually only asks
on a new device. The fix: log in once in a browser **on the same machine**, then run `fetch` again.
Cookies are saved after that, so it shouldn't ask again. If it keeps failing, stop retrying and
tell the user. Repeated failed logins can lock the account.

## Limits

- Unofficial. It reads the EasyEquities web pages, so it can break when they change the site. If
  holdings come back empty for an account that has them, say the site may have changed. Don't
  report a zero balance.
- A partial sale counts as a change in cost, not a realised gain, so a sale day's market move is
  approximate. A full sale is reported as flow and never counted as performance.
- Read-only. Nothing here can place, change or cancel a trade.
