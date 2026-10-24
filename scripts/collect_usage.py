"""Collect Claude Code usage from Claude Code's own files: counts, token totals and session titles only.

What you and Claude wrote is never kept or printed. Prompt text is looked at in memory only to tell
typed prompts from system rows, and to spot the optional web-refresh task's own sessions by MARKER,
which are left out of every count.

Usage:
  python3 collect_usage.py --json        print everything as one JSON object, UTF-8 (the panel reads this)
  python3 collect_usage.py --out DIR     write daily.json, hours.json, sessions.json, limits.json to DIR
                                         (for the optional web dashboard; limits.json comes from
                                         DIR/usage_raw.json when present)
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

MARKER = "[usage-calendar-refresh]"
ACTIVE_HOURS = 24
# A session still open in the desktop app is listed while it was used this recently
OPEN_SESSION_DAYS = 7
NOW = datetime.now().astimezone()

# API list prices, USD per million tokens: (input, output, cache read).
# Cache writes cost 1.25x input (5-minute TTL) or 2x input (1-hour TTL).
# Subscription plans don't bill this: the cost is "what the API would have charged".
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
CONTEXT_200K = {"claude-haiku-4-5"}
PARTS = ("input", "cacheWrite5m", "cacheWrite1h", "cacheRead", "output")


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def base_model(model):
    # Dated ids (claude-haiku-4-5-20251001) match their undated name
    return re.sub(r"-\d{8}$", "", model)


def context_window(model):
    m = base_model(model)
    if m not in PRICES:
        return None
    return 200_000 if m in CONTEXT_200K else 1_000_000


def desktop_session_files():
    """The desktop app's own record of each session, wherever this install keeps it."""
    roots = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        roots += [os.path.join(appdata, "Claude")]
        # Store installs keep their data in a folder of their own
        roots += glob.glob(os.path.join(local, "Claude-Data", "*"))
        roots += glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"))
    elif sys.platform == "darwin":
        roots.append(os.path.expanduser("~/Library/Application Support/Claude"))
    else:
        roots.append(os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "Claude"))
    files = []
    for root in roots:
        files += glob.glob(os.path.join(root, "claude-code-sessions", "**", "local_*.json"), recursive=True)
    return files


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def local(ts):
    """A transcript timestamp in this computer's time zone, or None when it doesn't parse."""
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def entries(path):
    """The rows of one transcript, one at a time; unreadable files and lines are skipped."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict):
                    yield e
    except OSError:
        return


def message_of(e):
    msg = e.get("message")
    return msg if isinstance(msg, dict) else {}


def text_of(e):
    content = message_of(e).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    return ""


def is_marker_row(e):
    """The refresh task's own prompt: it opens with MARKER, or arrives inside the task's wrapper."""
    if e.get("type") != "user":
        return False
    text = text_of(e).lstrip()
    if text.startswith(MARKER):
        return True
    # A scheduled run wraps its prompt in a tag that opens a line; a quote of it mid-line is someone's message
    wrapper = re.search(r"(?m)^<scheduled-task[^>]*>", text)
    return bool(wrapper) and MARKER in text[wrapper.end():]


def is_typed_prompt(e):
    """A prompt the person typed: not a tool result, a system row, a slash command or an interruption."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain"):
        return False
    content = message_of(e).get("content")
    if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        return False
    text = text_of(e).strip()
    has_image = isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "image" for c in content)
    if not text:
        return has_image
    return not text.startswith("<") and not text.startswith("[Request interrupted")


def usage_parts(u):
    split = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    one_hour = num(split.get("ephemeral_1h_input_tokens"))
    five_min = num(split.get("ephemeral_5m_input_tokens"))
    created = num(u.get("cache_creation_input_tokens")) or (one_hour + five_min)
    return {
        "input": num(u.get("input_tokens")),
        "cacheWrite5m": max(0, created - one_hour),
        "cacheWrite1h": min(one_hour, created),
        "cacheRead": num(u.get("cache_read_input_tokens")),
        "output": num(u.get("output_tokens")),
    }


def cost_of(model, parts):
    price = PRICES.get(base_model(model))
    if not price:
        return None
    inp, out, read = price
    return (parts["input"] * inp + parts["cacheWrite5m"] * inp * 1.25 + parts["cacheWrite1h"] * inp * 2
            + parts["cacheRead"] * read + parts["output"] * out) / 1e6


def context_size(u):
    # What one reply saw: all of its input, cached or not
    return num(u.get("input_tokens")) + num(u.get("cache_read_input_tokens")) + num(u.get("cache_creation_input_tokens"))


def read_stats_cache(home):
    """Claude Code's own daily totals, kept after old transcripts are deleted; empty when unreadable."""
    try:
        with open(os.path.join(home, "stats-cache.json"), encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        return {}, {}, {}
    if not isinstance(cache, dict):
        return {}, {}, {}

    def by_date(rows):
        return {r["date"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("date"), str)} if isinstance(rows, list) else {}

    activity = by_date(cache.get("dailyActivity"))
    tokens = {d: r.get("tokensByModel") for d, r in by_date(cache.get("dailyModelTokens")).items()
              if isinstance(r.get("tokensByModel"), dict)}
    usage = cache.get("modelUsage") if isinstance(cache.get("modelUsage"), dict) else {}
    return activity, tokens, usage


def estimate_parts(model_usage, model, total):
    """Split a day's total by the model's all-time shares: the cache keeps only the total."""
    mu = model_usage.get(model) if isinstance(model_usage.get(model), dict) else {}
    shares = {
        "input": num(mu.get("inputTokens")),
        "cacheWrite5m": 0,
        "cacheWrite1h": num(mu.get("cacheCreationInputTokens")),  # Claude Code writes 1-hour cache
        "cacheRead": num(mu.get("cacheReadInputTokens")),
        "output": num(mu.get("outputTokens")),
    }
    whole = sum(shares.values())
    if not whole:
        return {**dict.fromkeys(PARTS, 0), "input": total}
    parts = {k: int(total * v / whole) for k, v in shares.items()}
    parts["cacheRead"] += total - sum(parts.values())  # rounding left over lands on the biggest share
    return parts


def collect():
    home = config_dir()
    transcripts = glob.glob(os.path.join(home, "projects", "**", "*.jsonl"), recursive=True)

    desktop = {}
    for p in desktop_session_files():
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            desktop[d["cliSessionId"]] = {"title": d.get("title"), "archived": bool(d.get("isArchived"))}
        except (OSError, ValueError, KeyError, TypeError):
            pass

    # First pass: the refresh task's sessions, so that their subagents' files go too
    skipped = set()
    for path in transcripts:
        for e in entries(path):
            if is_marker_row(e) and e.get("sessionId"):
                skipped.add(e["sessionId"])

    days = defaultdict(lambda: {"messages": 0, "prompts": 0, "tools": 0, "sessions": set(),
                                "tokens": defaultdict(lambda: defaultdict(int))})
    hours = defaultdict(int)
    seen_rows = set()  # the same row is copied into resumed and forked sessions' files
    seen_msg = set()  # streamed replies repeat one message id
    sessions = {}

    for path in transcripts:
        title, last, sid_of_file = None, None, None
        for e in entries(path):
            sid = e.get("sessionId")
            if sid in skipped:
                break
            sid_of_file = sid_of_file or sid
            t = e.get("type")
            if t == "ai-title" and isinstance(e.get("aiTitle"), str):
                title = e["aiTitle"]
            if t not in ("user", "assistant"):
                continue
            when = local(e.get("timestamp"))
            if when is None:
                continue
            msg = message_of(e)
            model = msg.get("model") if isinstance(msg.get("model"), str) else ""
            u = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
            if t == "assistant" and u and model.startswith("claude") and not e.get("isSidechain"):
                last = (when, model, context_size(u), sid, e.get("entrypoint"))

            row_id = e.get("uuid")
            if row_id is not None:
                if row_id in seen_rows:
                    continue
                seen_rows.add(row_id)
            rec = days[when.date().isoformat()]
            rec["messages"] += 1
            if sid:
                rec["sessions"].add(sid)
            if is_typed_prompt(e):
                rec["prompts"] += 1
                hours[when.hour] += 1
            if t == "assistant":
                content = msg.get("content")
                if isinstance(content, list):
                    rec["tools"] += sum(1 for c in content if isinstance(c, dict) and c.get("type") == "tool_use")
                mid = msg.get("id")
                if mid and u and model.startswith("claude") and mid not in seen_msg:
                    seen_msg.add(mid)
                    for part, n in usage_parts(u).items():
                        rec["tokens"][model][part] += n

        if last:
            when, model, ctx, sid, entry = last
            meta = desktop.get(sid, {})
            age = NOW - when
            recent = age <= timedelta(hours=ACTIVE_HOURS)
            open_in_app = sid in desktop and not meta.get("archived") and age <= timedelta(days=OPEN_SESSION_DAYS)
            if (recent or open_in_app) and (sid not in sessions or sessions[sid]["lastActive"] < when.isoformat()):
                window = context_window(model)
                sessions[sid] = {
                    "session": sid,
                    "title": meta.get("title") or title,
                    "where": "desktop" if entry == "claude-desktop" or sid in desktop else "terminal",
                    "model": model,
                    "contextTokens": ctx,
                    "contextWindow": window,
                    "percentUsed": round(ctx / window * 100, 1) if window else None,
                    "lastActive": when.isoformat(timespec="minutes"),
                }

    # Claude Code deletes old transcripts after a while; those days live on only in stats-cache.json.
    # Its token totals count every streamed copy of a reply, so a day with transcripts uses them instead.
    cache_act, cache_tok, model_usage = read_stats_cache(home)

    rows = []
    for d in sorted(set(days) | set(cache_act) | set(cache_tok)):
        rec = days.get(d)
        if rec:
            parts = {m: dict(p) for m, p in rec["tokens"].items()}
            counts = {"messages": rec["messages"], "prompts": rec["prompts"],
                      "sessions": len(rec["sessions"]), "tools": rec["tools"]}
            is_estimated = False
        else:
            c = cache_act.get(d, {})
            parts = {m: estimate_parts(model_usage, m, num(n)) for m, n in cache_tok.get(d, {}).items()}
            counts = {"messages": num(c.get("messageCount")), "prompts": None,
                      "sessions": num(c.get("sessionCount")), "tools": num(c.get("toolCallCount"))}
            is_estimated = True
        by_model = {m: sum(p.values()) for m, p in parts.items()}
        priced = [(m, cost_of(m, p)) for m, p in parts.items()]

        def total(key):
            return sum(p.get(key, 0) for p in parts.values())

        rows.append({
            "date": d,
            **counts,
            "tokens": sum(by_model.values()),
            "topModel": max(by_model, key=by_model.get) if by_model else None,
            # All input the model read: uncached, cache writes and cache reads
            "inputTokens": total("input") + total("cacheWrite5m") + total("cacheWrite1h") + total("cacheRead"),
            "outputTokens": total("output"),
            "costUsd": round(sum(c for _, c in priced if c is not None), 4),
            # Tokens of models the price table doesn't know: in the totals, not in the cost
            "unpricedTokens": sum(by_model[m] for m, c in priced if c is None),
            "models": by_model,
            "isEstimated": is_estimated,
        })

    offset = NOW.utcoffset() or timedelta(0)
    return {
        "generatedAt": NOW.isoformat(timespec="minutes"),
        "today": NOW.date().isoformat(),
        "utcOffsetMinutes": int(offset.total_seconds() // 60),
        "days": rows,
        "hours": [{"hour": h, "prompts": hours[h]} for h in range(24)],
        "sessions": sorted(sessions.values(), key=lambda s: s["lastActive"], reverse=True),
    }


def limits_from(out_dir):
    """usage_raw.json: the plan part of Claude Code's usage reading, left there by the web task."""
    path = os.path.join(out_dir, "usage_raw.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        plan = raw.get("plan") if isinstance(raw, dict) else None
        windows = plan.get("windows") if isinstance(plan, dict) else None
        if not isinstance(windows, list):
            return None
    except (OSError, ValueError):
        return None
    fetched = datetime.fromtimestamp(os.path.getmtime(path)).astimezone().isoformat(timespec="minutes")
    return [{"limit": w.get("label"), "percentUsed": w.get("percentUsed"), "resetsAt": w.get("resetsAt"),
             "plan": plan.get("plan"), "fetchedAt": fetched} for w in windows if isinstance(w, dict)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print everything as one JSON object")
    ap.add_argument("--out", metavar="DIR", help="write the web dashboard's JSON files to DIR")
    args = ap.parse_args()
    if not args.json and not args.out:
        ap.error("pass --json or --out DIR")

    data = collect()
    if args.json:
        # Bytes, not text: a Windows pipe would otherwise use the console's code page
        sys.stdout.buffer.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        sys.stdout.flush()
    if args.out:
        out = os.path.expanduser(os.path.expandvars(args.out))  # "~" too, where the shell leaves it alone
        os.makedirs(out, exist_ok=True)
        files = {"daily.json": data["days"], "hours.json": data["hours"], "sessions.json": data["sessions"]}
        limits = limits_from(out)
        if limits is not None or not os.path.exists(os.path.join(out, "limits.json")):
            files["limits.json"] = limits or []
        for name, value in files.items():
            with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
                json.dump(value, fh, indent=1, ensure_ascii=False)
        if not args.json:
            print(f"{len(data['days'])} active days, {len(data['sessions'])} sessions -> {out}")


if __name__ == "__main__":
    main()
