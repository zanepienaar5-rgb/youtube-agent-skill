---
name: ee-ask
description: >-
  Answer a specific question about the user's EasyEquities or Satrix
  accounts from live data: a holding's P/L, dividends received, what was
  bought or sold in a period, fees paid, how an ETF has done over 3 months,
  or what they hold most of. Use for any EasyEquities / Satrix / "my shares" /
  "my TFSA" question that isn't the daily brief.
---

# ee-ask

One question, answered from the real numbers. For the daily summary, use `/ee-brief` instead.

## Where the data comes from

1. **The `easy-equities` MCP tools**, if this client has them (this plugin wires them up). Map the
   question to the fewest calls:

   | question | calls |
   | --- | --- |
   | what do I hold / P/L on X | `list_accounts` -> `get_holdings` |
   | how many shares of X | `get_holdings(..., include_shares=true)`. Slower, one request per holding |
   | cash, account value, costs | `get_valuations` |
   | dividends, fees, deposits, buys in the last year | `get_transactions` |
   | the same for a specific range | `get_transactions_for_period(start, end)` as YYYY-MM-DD |
   | how has X done over a period | `get_holdings` for its `contract_code` -> `get_historical_prices(code, period)` |

   Start with `list_sessions`. If there's only one session and one obvious account, don't ask the
   user which one.
2. **No MCP?** Use the latest snapshot: `python3 ../ee-brief/eebrief.py brief --json`, or read
   `~/.easy-equities-mcp/snapshots/<date>.json` directly. Say how old it is.
3. **A login error:** `refresh_session(name)` once. If that fails, follow the OTP steps in
   `ee-brief`. Don't keep retrying.

## Answering

- The number first, then what it's made of, then one line of context if it helps.
  "R2 140 in dividends since March: Satrix 40 R1 310, Capitec R830." Don't open with a table of
  every transaction.
- Amounts come back as strings like `R 1 234.56`. Parse them carefully. Never add ZAR to USD.
- For a sum over transactions (dividends, fees, deposits), show the rows you counted when there are
  ten or fewer. Transaction descriptions vary, so say what you matched on.
- `get_transactions` only covers the last year. For older questions use
  `get_transactions_for_period`, and say if the answer may be incomplete.
- If the data can't answer it (tax certificates, cost of a closed position from years ago), say so
  and point them to the place in EasyEquities that can.

## Never

- Never ask for or repeat a password. Credentials live in the `.env` file, not in chat.
- No buy or sell recommendations, targets or forecasts. Facts and the arithmetic on them only.
- Never claim a trade was placed. Nothing in this plugin can trade.
