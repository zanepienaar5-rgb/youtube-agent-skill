# EasyEquities plugin

Your EasyEquities and Satrix accounts in Claude. It has two skills, it is read-only, and it never
sees your password in chat.

| command | what it does |
| --- | --- |
| `/ee-brief` | The daily brief: every account's value, what the **market** did since yesterday with your own buys and deposits taken out, the biggest movers, concentration, and TFSA room left this tax year. |
| `/ee-ask` | One question answered from live data: dividends since March, P/L on a holding, what you bought last month, how an ETF did over 3 months. |

It wraps [heinrich321/easyequities-mcp](https://github.com/heinrich321/easyequities-mcp), which this
plugin starts for you, and adds `eebrief.py`, a no-dependency snapshot tool. The snapshots are what
make day-on-day change possible, because EasyEquities only ever shows you the current position.

## Install (Claude Code)

```
/plugin marketplace add zanepienaar5-rgb/youtube-agent-skill
/plugin install easyequities
```

Needs [`uv`](https://docs.astral.sh/uv/) on your PATH. The plugin launches the MCP with `uvx`, and
uv fetches Python 3.13 itself if you don't have it.

## One-time setup

1. Create `~/.config/easy-equities-mcp/.env` and lock it down (`chmod 600`):
   ```
   EE_SESSION_PERSONAL_USERNAME=your-login
   EE_SESSION_PERSONAL_PASSWORD=your-password
   EE_SESSION_PERSONAL_PLATFORM=easyequities
   ```
   One login covers all its accounts (ZAR, USD, TFSA). Add a second block for a separate Satrix
   login (`PLATFORM=satrix`).
2. Log in to easyequities.co.za once in a browser **on the same computer**. That clears the
   new-device OTP, which the library can't answer.
3. `pip install easy-equities-client` (only needed for `eebrief.py fetch`), then:
   ```bash
   python3 skills/ee-brief/eebrief.py sessions   # should say user set, password set
   python3 skills/ee-brief/eebrief.py fetch      # first snapshot
   ```

## Make it daily

Take a snapshot every weekday after the JSE closes, even on days you don't open Claude
(`crontab -e`):

```
15 18 * * 1-5 python3 /full/path/to/eebrief.py fetch >> ~/.easy-equities-mcp/fetch.log 2>&1
```

Then each morning, run `/ee-brief`.

## Fine print

- **Unofficial.** It reads the EasyEquities web pages, so a site redesign can break it until the
  library is updated. You're responsible for your credentials and for EasyEquities' terms.
- **Read-only.** Nothing here can place, change or cancel a trade, and the skills won't give buy or
  sell advice.
- **The TFSA figure is an estimate** from transaction descriptions, against a R36 000 annual limit
  by default (`EE_TFSA_ANNUAL_LIMIT` to change it). SARS taxes excess contributions at 40%, so check
  EasyEquities' own tracker before you top up near the limit.
- **ZAR and USD are never added together.** No FX rate is assumed.
- Cookies and snapshots live in `~/.easy-equities-mcp/` with owner-only permissions. Anyone who can
  read that folder can see your portfolio and reuse the login.
- The plugin pins the MCP SDK below 2.0 (`--with "mcp[cli]<2"`) because upstream breaks on SDK 2.x
  (`FastMCP` was renamed). You can drop the pin once upstream is updated.
