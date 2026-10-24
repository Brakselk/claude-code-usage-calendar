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
import math
import os
import re
import statistics
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
# Session titles in transcripts: the row type and the field holding the title.
# custom-title is a rename (the person's or the desktop app's); ai-title is Claude's own guess.
TITLE_FIELDS = {"custom-title": "customTitle", "ai-title": "aiTitle"}
# Blocks Claude Code puts in front of what the person typed
INJECTED = re.compile(r"\s*(?:<system-reminder\b[^>]*>.*?</system-reminder>"
                      r"|<artifact-view-context\b[^>]*>.*?</artifact-view-context>)", re.S)
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def env_dir(name):
    """A folder named by an environment variable, or None: unset, empty or relative would mean the current folder."""
    value = os.environ.get(name, "")
    return value if os.path.isabs(value) else None


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
        appdata, local = env_dir("APPDATA"), env_dir("LOCALAPPDATA")
        if appdata:
            roots.append(os.path.join(appdata, "Claude"))
        if local:
            # Store installs keep their data in a folder of their own
            roots += glob.glob(os.path.join(local, "Claude-Data", "*"))
            roots += glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"))
    elif sys.platform == "darwin":
        roots.append(os.path.expanduser("~/Library/Application Support/Claude"))
    else:
        roots.append(os.path.join(env_dir("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "Claude"))
    files = []
    for root in roots:
        files += glob.glob(os.path.join(root, "claude-code-sessions", "**", "local_*.json"), recursive=True)
    return files


def num(x):
    """A count or token total, else 0.

    NaN, Infinity (json.loads accepts both), negatives and absurd sizes become 0 too: the output must
    stay valid JSON for JavaScript, and sums and costs must stay finite. No real count is near 1e15.
    """
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return 0
    return x if 0 <= x <= 1e15 else 0


def local(ts):
    """A transcript timestamp in this computer's time zone, or None when it doesn't parse."""
    if not isinstance(ts, str):
        return None
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, OSError, OverflowError):
        # Windows can't convert times before 1970 or after 3000; years 1 and 9999 overflow in some zones
        return None
    # Windows' range everywhere, so Linux and macOS don't list days that Windows skips
    return when if 1970 <= when.year < 3000 else None


def is_day(s):
    """A plain YYYY-MM-DD that is a real date; anything else would make a broken day in the calendar."""
    if not isinstance(s, str) or not DAY.fullmatch(s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def entries(path, only_with=()):
    """The rows of one transcript, one at a time; unreadable files and lines are skipped.

    With only_with, a line is parsed only when it contains one of those strings: parsing is the slow part.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if only_with and not any(s in line for s in only_with):
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):  # RecursionError: absurdly nested junk
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


def session_of(e):
    # Ids go into sets: anything but a string (a list, say) would crash the run
    sid = e.get("sessionId")
    return sid if isinstance(sid, str) and sid else None


def is_marker_row(e):
    """The refresh task's own prompt: it opens with MARKER, or arrives inside the task's wrapper."""
    # A subagent's prompt is written by its parent session: quoting MARKER there must not drop the parent
    if e.get("type") != "user" or e.get("isSidechain"):
        return False
    # A pasted or file-read prompt can open with a byte order mark, which isn't whitespace to lstrip()
    text = text_of(e).lstrip().lstrip("﻿").lstrip()
    if text.startswith(MARKER):
        return True
    # A scheduled run wraps its prompt in a tag that opens a line; a quote of it mid-line is someone's message
    wrapper = re.search(r"(?m)^<scheduled-task[^>]*>", text)
    return bool(wrapper) and MARKER in text[wrapper.end():]


def strip_injected(text):
    """The text past any system-reminder and artifact-view-context blocks it opens with."""
    m = INJECTED.match(text)
    while m:
        text = text[m.end():]
        m = INJECTED.match(text)
    return text


def is_typed_prompt(e):
    """A prompt the person typed: not a tool result, a system row, a slash command or an interruption."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain"):
        return False
    # A compacted conversation's summary and rows shown only in the transcript are Claude Code's own
    if e.get("isCompactSummary") or e.get("isVisibleInTranscriptOnly"):
        return False
    content = message_of(e).get("content")
    if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        return False
    origin = e.get("origin")
    if isinstance(origin, dict):
        # Newer Claude Code says who wrote the row, and a typed prompt may still open with an injected block
        return origin.get("kind") == "human"
    # Older Claude Code: tell from the text, past the blocks put in front of what was typed
    text = strip_injected(text_of(e)).strip()
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
    except (OSError, ValueError, RecursionError):
        return {}, {}, {}
    if not isinstance(cache, dict):
        return {}, {}, {}

    def by_date(rows):
        return {r["date"]: r for r in rows if isinstance(r, dict) and is_day(r.get("date"))} if isinstance(rows, list) else {}

    activity = by_date(cache.get("dailyActivity"))
    tokens = {d: r.get("tokensByModel") for d, r in by_date(cache.get("dailyModelTokens")).items()
              if isinstance(r.get("tokensByModel"), dict)}
    usage = cache.get("modelUsage") if isinstance(cache.get("modelUsage"), dict) else {}
    return activity, tokens, usage


def cache_overcount(days, cache_act, cache_tok):
    """How much stats-cache.json overcounts messages and tokens: the median cache/transcript ratio
    over days that have both, per measure, or None for a measure no day has both of.

    It counts every streamed copy of a reply (real data: ~1.6x messages, ~2.6x tokens);
    its sessions and tool calls match the transcripts, so they are left alone.
    """
    messages, tokens = [], []
    for d, rec in days.items():
        cached = num(cache_act.get(d, {}).get("messageCount"))
        if cached and rec["messages"]:
            messages.append(cached / rec["messages"])
        cached = sum(num(n) for n in cache_tok.get(d, {}).values())
        counted = sum(sum(p.values()) for p in rec["tokens"].values())
        if cached and counted:
            tokens.append(cached / counted)
    return {"messages": statistics.median(messages) if messages else None,
            "tokens": statistics.median(tokens) if tokens else None}


def shrink(value, factor):
    return int(round(value / factor)) if factor else value


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
    # Sorted, so that ties between copies of a row resolve the same way on every run and system
    transcripts = sorted(glob.glob(os.path.join(home, "projects", "**", "*.jsonl"), recursive=True))

    desktop = {}
    for p in desktop_session_files():
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError, RecursionError):
            continue
        # Only the app's own record: a JSON object with a session id
        if not isinstance(d, dict) or not isinstance(d.get("cliSessionId"), str):
            continue
        title = d.get("title")
        desktop[d["cliSessionId"]] = {"title": title if isinstance(title, str) else None,
                                      "archived": bool(d.get("isArchived"))}

    # First pass: the refresh task's sessions, so that their subagents' files go too.
    # Its prompt always contains MARKER, so lines without it (or the wrapper) aren't parsed at all.
    skipped = set()
    for path in transcripts:
        for e in entries(path, only_with=(MARKER, "<scheduled-task")):
            sid = session_of(e)
            if sid and is_marker_row(e):
                skipped.add(sid)

    days = defaultdict(lambda: {"messages": 0, "prompts": 0, "tools": 0, "sessions": set(),
                                "tokens": defaultdict(lambda: defaultdict(int))})
    hours = defaultdict(int)
    seen_rows = set()  # the same row is copied into resumed and forked sessions' files
    seen_msg = set()  # streamed replies repeat one message id
    # Per session id, over all files: a session's rows and titles are copied into forks and subagents
    last_reply = {}  # sessionId -> (when, model, context, entrypoint) of its latest main-thread reply
    titles = {}  # sessionId -> {row type: (from the session's own file, title)}

    for path in transcripts:
        # A session's own file is named after it; other files only carry copies of its rows
        stem = os.path.splitext(os.path.basename(path))[0]
        for e in entries(path):
            sid = session_of(e)
            if sid in skipped:
                continue  # just the task's rows: a fork can start with rows copied from it
            t = e.get("type")
            field = TITLE_FIELDS.get(t)
            if sid and field and isinstance(e.get(field), str) and e[field]:
                own = sid == stem
                kept = titles.setdefault(sid, {}).get(t)
                # A later row wins, but a copy in another file never beats the session's own file
                if kept is None or own or not kept[0]:
                    titles[sid][t] = (own, e[field])
            if t not in ("user", "assistant"):
                continue
            when = local(e.get("timestamp"))
            if when is None:
                continue
            msg = message_of(e)
            model = msg.get("model") if isinstance(msg.get("model"), str) else ""
            u = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
            if t == "assistant" and u and model.startswith("claude") and not e.get("isSidechain") and sid:
                # Compare times, not minute strings: copies in several files must not hide the latest
                if sid not in last_reply or when >= last_reply[sid][0]:
                    last_reply[sid] = (when, model, context_size(u), e.get("entrypoint"))

            row_id = e.get("uuid")
            if isinstance(row_id, str):
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
                if isinstance(mid, str) and mid and u and model.startswith("claude") and mid not in seen_msg:
                    seen_msg.add(mid)
                    for part, n in usage_parts(u).items():
                        rec["tokens"][model][part] += n

    sessions = []
    for sid, (when, model, ctx, entry) in last_reply.items():
        meta = desktop.get(sid, {})
        age = NOW - when
        recent = age <= timedelta(hours=ACTIVE_HOURS)
        open_in_app = sid in desktop and not meta.get("archived") and age <= timedelta(days=OPEN_SESSION_DAYS)
        if not (recent or open_in_app):
            continue
        named = titles.get(sid, {})
        window = context_window(model)
        sessions.append((when, {
            "session": sid,
            # The title the desktop app shows, else a rename, else Claude's own guess
            "title": meta.get("title") or named.get("custom-title", (0, None))[1] or named.get("ai-title", (0, None))[1],
            "where": "desktop" if entry == "claude-desktop" or sid in desktop else "terminal",
            "model": model,
            "contextTokens": ctx,
            "contextWindow": window,
            "percentUsed": round(ctx / window * 100, 1) if window else None,
            "lastActive": when.isoformat(timespec="minutes"),
        }))
    sessions.sort(key=lambda s: s[0], reverse=True)

    # Claude Code deletes old transcripts after a while; those days live on only in stats-cache.json.
    # Its message and token totals count every streamed copy of a reply, so a day with transcripts uses
    # them instead, and a cache-only day is divided by how much the cache overcounts the other days.
    cache_act, cache_tok, model_usage = read_stats_cache(home)
    over = cache_overcount(days, cache_act, cache_tok)

    rows = []
    for d in sorted(set(days) | set(cache_act) | set(cache_tok)):
        rec = days.get(d)
        if rec:
            parts = {m: dict(p) for m, p in rec["tokens"].items()}
            counts = {"messages": rec["messages"], "prompts": rec["prompts"],
                      "sessions": len(rec["sessions"]), "tools": rec["tools"]}
            is_estimated, scaled = False, None
        else:
            c = cache_act.get(d, {})
            parts = {m: estimate_parts(model_usage, m, shrink(num(n), over["tokens"]))
                     for m, n in cache_tok.get(d, {}).items()}
            counts = {"messages": shrink(num(c.get("messageCount")), over["messages"]), "prompts": None,
                      "sessions": num(c.get("sessionCount")), "tools": num(c.get("toolCallCount"))}
            is_estimated = True
            scaled = ({k: round(f, 3) if f else None for k, f in over.items()}
                      if over["messages"] or over["tokens"] else None)
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
            # Cache-only days: what the cache's messages and tokens were divided by,
            # {"messages": f or null, "tokens": f or null}; null on transcript days and when no day overlaps
            "scaledFromCache": scaled,
        })

    offset = NOW.utcoffset() or timedelta(0)
    return {
        "generatedAt": NOW.isoformat(timespec="minutes"),
        "today": NOW.date().isoformat(),
        "utcOffsetMinutes": int(offset.total_seconds() // 60),
        "days": rows,
        "hours": [{"hour": h, "prompts": hours[h]} for h in range(24)],
        "sessions": [s for _, s in sessions],
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
        fetched = datetime.fromtimestamp(os.path.getmtime(path)).astimezone().isoformat(timespec="minutes")
    except (OSError, ValueError, OverflowError, RecursionError):
        return None

    # Only strings and finite numbers pass through, so limits.json stays valid JSON
    def text(x):
        return x if isinstance(x, str) else None

    def percent(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None

    return [{"limit": text(w.get("label")), "percentUsed": percent(w.get("percentUsed")),
             "resetsAt": text(w.get("resetsAt")), "plan": text(plan.get("plan")), "fetchedAt": fetched}
            for w in windows if isinstance(w, dict)]


def say(stream, text):
    # Bytes, not text: a Windows pipe would otherwise use the console's code page and fail on other characters.
    # "replace": a title cut mid-emoji holds half a surrogate pair, which UTF-8 can't encode
    stream.buffer.write(text.encode("utf-8", "replace"))
    stream.flush()


def fail(message, code=2):
    say(sys.stderr, f"collect_usage.py: error: {message}\n")
    sys.exit(code)


def write_json(path, value):
    """Write to a temporary file in the same folder, then swap it in: a reader never sees half a file."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", errors="replace") as fh:  # "replace": see say()
            json.dump(value, fh, indent=1, ensure_ascii=False, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print everything as one JSON object")
    ap.add_argument("--out", metavar="DIR", help="write the web dashboard's JSON files to DIR")
    args = ap.parse_args()
    if not args.json and args.out is None:
        ap.error("pass --json or --out DIR")

    out = None
    if args.out is not None:
        # Checked before collecting: a bad folder is a one-line error, not a traceback at the end
        out = os.path.expanduser(os.path.expandvars(args.out))  # "~" too, where the shell leaves it alone
        if not out.strip():
            fail("--out needs a folder name")
        if os.path.exists(out) and not os.path.isdir(out):
            fail(f"--out {out} is a file, not a folder")
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as err:
            fail(f"--out {out}: can't create the folder ({err.strerror or err})")

    data = collect()
    if args.json:
        say(sys.stdout, json.dumps(data, ensure_ascii=False, allow_nan=False))
    if out is not None:
        files = {"daily.json": data["days"], "hours.json": data["hours"], "sessions.json": data["sessions"]}
        limits = limits_from(out)
        if limits is not None or not os.path.exists(os.path.join(out, "limits.json")):
            files["limits.json"] = limits or []
        try:
            for name, value in files.items():
                write_json(os.path.join(out, name), value)
        except OSError as err:
            fail(f"--out {out}: can't write ({err.strerror or err})", code=1)
        if not args.json:
            say(sys.stdout, f"{len(data['days'])} active days, {len(data['sessions'])} sessions -> {out}\n")


if __name__ == "__main__":
    main()
