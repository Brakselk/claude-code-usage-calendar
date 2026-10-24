# Optional: a web version of the calendar

[Türkçe](web-dashboard.tr.md)

The panel needs nothing else. If you also want the calendar as a page you can open in a browser (on claude.ai, private to you unless you share it), Claude can build one from the same numbers and keep it fresh with a scheduled task. This part can't ship inside the plugin: the page lives in your claude.ai account, and the task runs in your Claude Code.

What goes on that page: your daily numbers, limits, and the titles and ids of sessions from the last day. Leave this out if you'd rather none of that left your computer.

Below, `<SCRIPT>` is the path to `scripts/collect_usage.py`: in a clone of this repository, or in the installed plugin's folder (`claude plugin list` shows where it is read from). Use `python` instead of `python3` where that is your Python's name, as on most Windows machines.

## 1. Write the numbers to a folder

```bash
python3 <SCRIPT> --out ~/.claude/usage-calendar-web
```

This writes `daily.json`, `hours.json`, `sessions.json` and `limits.json` there; the script expands `~` itself, so this works in PowerShell and cmd too. (`limits.json` stays empty until step 3's task has run once.)

## 2. Ask Claude to build the page

In a Claude Code session in the desktop app, ask something like:

> Build me a claude.ai dashboard from the JSON files in `~/.claude/usage-calendar-web`, with one dataset per file named `daily`, `hours`, `sessions` and `limits`: a GitHub-style heatmap of daily usage from `daily`, usage limits from `limits`, active sessions from `sessions` and prompts by hour from `hours`.

Claude publishes it and gives you a link. Keep that link: it is your `webUrl`.

## 3. Keep it fresh with a scheduled task

Ask Claude to create a scheduled task (for example every morning) with the prompt below. Replace `<DASHBOARD_URL>`, `<FOLDER>` (the folder from step 1) and `<SCRIPT>`, and note the task id Claude gives it: that is your `webRefreshTask`.

Keep the first line exactly as it is. A session whose prompt opens with that marker is the task's own run, and the calendar leaves it (and its subagents) out of your numbers. Mentioning the marker anywhere else in a message changes nothing.

```text
[usage-calendar-refresh]
Refresh the Claude Code Usage Calendar dashboard at <DASHBOARD_URL>. Do only these steps and change nothing else. If a step fails, stop and say in one line which step it was.

1. Load the tools with ToolSearch: "select:mcp__ccd_session_mgmt__get_usage,ArtifactData".
2. Call mcp__ccd_session_mgmt__get_usage with no arguments. If plan.status is "ok", write the JSON it returns, unchanged, to <FOLDER>/usage_raw.json with the Write tool.
3. Run: python3 <SCRIPT> --out <FOLDER>
4. Upload each of daily.json, hours.json, sessions.json and limits.json from <FOLDER> to the dashboard with its own Artifact call (url: <DASHBOARD_URL>, asset: true), and note each new "/_blob/<id>" address.
5. Read the dashboard's datasets (ArtifactData action "list", collection "datasets") and note each one's version and current source.url.
6. In one ArtifactData "batch", update the datasets daily, hours, sessions and limits so each source is its new file ({"kind": "file", "url": "<new /_blob/ address>", "name": "<file name>"}) and its updated field is {"at": "<now, ISO 8601>", "by": "Scheduled task"}, pinned with if_version.
7. If the batch succeeded, delete the four old files (Artifact action "delete", path: the 32-character id from each old source.url).
8. Finish with one line: how many days and sessions were uploaded.
```

## 4. Point the panel at it

Set `webUrl` to the dashboard link and `webRefreshTask` to the task id, in `/config` under the plugin. The panel then shows **Open on web** and **Update web too**.

Scheduled tasks run while the Claude app is open; one that was due while it was closed runs the next time you open it. Save the task in Auto mode, or it stops and waits for you to approve its steps (writing `usage_raw.json` and running the script).
