# Changelog

## 0.2.1 — 2026-10-24

### Fixed
- In the Claude desktop app the panel never opened or refreshed on its own (a 0.2.0 regression): the app starts sessions headless and attaches its window afterwards. The panel now starts when a window attaches, and a `-p` run still never runs Python or opens it.
- A pane closed with × stays closed for that session, even when the plugin reloads; `/usage-calendar` opens it again.
- Switching language now retitles the open pane and the command's description.
- An old "Refresh failed" line no longer stays under fresh numbers another session kept.
- A `|` in a model name no longer breaks the days table.
- A missing usage script says so instead of "Python was not found"; a Python 2 that can't read the script makes way for the next Python; an exit code reads in the panel's language.
- The heatmap's description counts only the days the heatmap draws; this session shows as Terminal in a terminal; limit windows that leave are no longer shown as live; kept data whose time doesn't parse is ignored instead of showing "NaN".
- Script: a malformed desktop session file, an out-of-range timestamp, odd ids or deeply nested junk no longer crash the run; prompts typed after an injected system block are counted (they carry Claude Code's own `origin` marker), compaction summaries are not; the session list keeps the truly latest reply and the right title across files, preferring the desktop app's title, then a rename, then Claude's guess; `--out` summaries and titles cut mid-emoji print safely on any console.

### Changed
- Only one open session runs an automatic count at a time (a lock in the plugin's store); a press of Refresh always runs.
- Days known only from `stats-cache.json` are divided by the overcount measured on days that have both (new day field `scaledFromCache`).
- A marker quoted inside a subagent no longer drops its parent session, and a fork that starts with the refresh task's copied rows still counts its own.
- `--out` writes each file atomically, rejects an empty or non-folder path with a one-line error, and output never contains NaN or negative counts. Unset `APPDATA`/`LOCALAPPDATA` no longer means the current folder.
- The first pass over transcripts only parses lines that can hold the marker (about 2.5× faster there).
- Docs: where to find the script after an install, how to set the options (`/plugin configure`, `--config`, `--values-stdin`), a more accurate privacy note, Python 3.7+, and the Turkish guide carries the task prompt itself.

### Tests
- Script tests 10 → 28; panel tests 15 → 26.

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
