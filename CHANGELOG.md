# Changelog

## 0.2.0 — 2026-10-24

Fixes from a full review of the panel and the data script.

### Numbers
- Rows copied into resumed and forked sessions' transcripts were counted again; each row now counts once. On busy days messages, prompts and tool calls had been several times too high.
- Days that still have transcripts no longer take Claude Code's `stats-cache.json` token totals, which count every streamed copy of a reply. Tokens and estimated cost had been about 2.4× too high on such days.
- Prompts count only what you typed: slash commands, system rows and interruptions are left out.
- The web-refresh task's own sessions are recognized only by a prompt that opens with the marker (or the scheduled-task wrapper), and their subagents are left out too. A message that merely mentions the marker is counted.
- Days found only in `dailyModelTokens` are included; cache writes never go negative; tokens of models without a known price are reported, not silently left out of the cost.

### Reliability
- The script prints UTF-8 bytes, so a session title with emoji or Turkish letters no longer crashes or garbles a refresh on Windows.
- Session titles are found in the Claude desktop app's Store-install folder as well.
- One unreadable file or malformed row no longer stops the whole run.
- `--out ~/…` works in PowerShell and cmd; `CLAUDE_CONFIG_DIR` is honored.
- The panel checks the script's output before keeping it, tells a missing Python apart from a failing one, and never runs two refreshes at once or stays stuck on "Refreshing…" after a reload.
- Headless sessions (`-p`, SDK, scheduled tasks) no longer run Python or open the panel.

### Panel
- Limits from an earlier session show until the new session's first reply, marked "as of" rather than "live".
- The half-hourly refresh is quiet; only a press of Refresh shows a toast. It also skips the run when another open session has just refreshed.
- The heatmap's color scale follows the weeks on screen.
- 999,960 reads "1 M", not "1,000 K".
- The pane title, command description and messages follow the panel's language; color buttons have names a screen reader can read; the heatmap's description says what it shows.
- An invalid `webUrl` is ignored instead of breaking the pane.

### Repository
- Tests for the data script (`tests/test_collect_usage.py`) and more panel tests, a plugin icon, `.gitattributes`, and a Turkish version of the web-dashboard guide.

## 0.1.0 — 2026-10-24

First release.
