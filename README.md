<p align="center">
  <img src="docs/banner.svg" alt="Token Garden: a year of daily Claude Code activity as a heatmap, with most used model, peak month, longest streak and estimated cost" width="100%">
</p>

<p align="center">
  <b>A GitHub-style calendar of your Claude Code usage, in a side panel next to the chat.</b><br>
  Daily heatmap · live plan limits · context fill per session · tokens and estimated cost
</p>

<p align="center">
  <a href="README.tr.md">Türkçe</a> ·
  <a href="#install">Install</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#privacy">Privacy</a>
</p>

---

## What you get

<img src="docs/panel.svg" alt="The panel: summary tiles, the daily heatmap with metric and color choices, usage limits and active sessions" width="46%" align="right">

**Daily activity heatmap.** One square per day for the last 6 or 12 months. Switch between messages, prompts, sessions, tool calls and tokens. Hover a square to read that day.

**Summary tiles.** Active days, messages, sessions, tool calls, tokens, your most used model, your peak month, and your longest and current streak.

**Usage limits, live.** Your plan's 5-hour and weekly limits with how much is used and when each resets. The numbers come straight from Claude Code and move as you work.

**Context fill per session.** Every session from the last 24 hours, with how full its context window is. The one you are in updates live.

**Token details.** Input, output and total tokens, plus what the same usage would cost at API list prices.

**Time of day and a day-by-day table**, each in a section you can open and close.

**Yours to tune.** English or Turkish with one press (`TR` / `EN`), seven accent colors, and the panel remembers what you chose.

<br clear="right">

<p align="center">
  <img src="docs/colors.svg" alt="The seven accent colors: Clay, Ocean, Forest, Violet, Rose, Amber, Teal" width="100%">
</p>

> The pictures above are drawn from made-up sample data.

## Install

You need **Claude Code 2.1.308 or later** and **Python 3** (`python3`, `python` or `py` on your PATH). The panel draws its charts in the Claude desktop app; in a terminal it shows the same numbers as text.

At the prompt of a Claude Code terminal session:

```
/plugin install token-garden --marketplace Brakselk/token-garden
```

Answer `y` to add the marketplace, then pick a scope (Enter takes the user scope). From a shell instead:

```bash
claude plugin install token-garden --marketplace Brakselk/token-garden
```

In the desktop app, where `/plugin` does not run: click **+** next to the prompt box, then **Plugins**, **Add marketplace** with `Brakselk/token-garden`, then **Add plugin**.

> While this repository is private, installing works only for people who can read it on GitHub and whose computer already has a git credential for github.com (an SSH key, or `gh auth login` then `gh auth setup-git`).

## Use

- The panel opens by itself in every session. Its × closes it for that session only; `/token-garden` opens it again.
- **Refresh** (or `R` while the panel has the keyboard) recounts your usage. It also refreshes on its own at the start of a session and every 30 minutes.
- **TR / EN** switches the language, the dots next to **Color** switch the accent, and each section title opens or closes it.

## Settings

Both are optional and empty by default. Set them in `/config` under the plugin, or when you install it.

| Setting | What it does |
|---|---|
| `webUrl` | A link to a web version of the dashboard. Shows an **Open on web** link in the panel. |
| `webRefreshTask` | The id of a Claude Code scheduled task that refreshes that web version. Shows an **Update web too** button. |

How to make that web version is in [docs/web-dashboard.md](docs/web-dashboard.md).

## Privacy

- Everything runs on your computer. The panel reads Claude Code's own files under `~/.claude` (session transcripts and `stats-cache.json`) and the desktop app's session list, and keeps its numbers in the plugin's local store. Nothing is uploaded.
- The script counts messages, tool calls and tokens and reads session titles. It does not read what you or Claude wrote. The one exception: it looks for the marker `[token-garden-refresh]` so that the optional web-refresh task's own sessions are left out of your numbers.
- Limits and context fill come from Claude Code itself, through the plugin API.

## How the numbers are counted

- **Messages** are every line you and Claude wrote in a session, tool results included. **Prompts** are only the messages you typed.
- **Tokens** add up input, cache writes, cache reads and output for each reply, once per reply.
- **Estimated cost** uses API list prices per model, with cache writes at 1.25× (5-minute) or 2× (1-hour) the input price. Subscription plans don't bill this; it shows what the same usage would cost on the API.
- Claude Code deletes old transcripts after a while. For those days only the totals in `stats-cache.json` remain, so their input/output split is estimated from your overall shares, and the panel says so.

## Limitations

- Only Claude Code sessions on this computer are counted. Chats on claude.ai and other computers are not.
- The plugin API this panel is built on is in early access and can change between Claude Code releases.
- Prices are built into `scripts/collect_usage.py` and need updating when list prices change.

## Credits

Made by [Brakselk](https://github.com/Brakselk), built together with [Claude Code](https://claude.com/claude-code).

## License

[MIT](LICENSE)
