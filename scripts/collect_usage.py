"""Collect Claude Code usage from ~/.claude: counts, token totals and session titles only.

Message text is never read, except to spot the optional web-refresh task's own sessions
by MARKER, which are left out of every count.

Usage:
  python3 collect_usage.py --json        print everything as one JSON object (the panel reads this)
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

HOME = os.path.expanduser("~/.claude")
MARKER = "[usage-calendar-refresh]"
ACTIVE_HOURS = 24
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
PARTS = ("input", "cacheWrite5m", "cacheWrite1h", "cacheRead", "output")


def base_model(model):
    # Dated ids (claude-haiku-4-5-20251001) match their undated name
    return re.sub(r"-\d{8}$", "", model)


def context_window(model):
    m = base_model(model)
    if m in PRICES:
        return 200_000 if m == "claude-haiku-4-5" else 1_000_000
    return None


def desktop_sessions_dir():
    if sys.platform == "win32":
        root = os.environ.get("APPDATA", "")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, "Claude", "claude-code-sessions")


def local(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()


def usage_parts(u):
    created = u.get("cache_creation_input_tokens", 0) or 0
    one_hour = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) or 0
    return {
        "input": u.get("input_tokens", 0) or 0,
        "cacheWrite5m": created - one_hour,
        "cacheWrite1h": one_hour,
        "cacheRead": u.get("cache_read_input_tokens", 0) or 0,
        "output": u.get("output_tokens", 0) or 0,
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
    return sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def is_prompt(e):
    if e.get("isMeta") or e.get("isSidechain"):
        return False
    content = (e.get("message") or {}).get("content")
    return not (isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content))


def prompt_text(e):
    content = (e.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def collect():
    # The desktop app's own record of each session: its title and whether it is archived
    desktop = {}
    for p in glob.glob(os.path.join(desktop_sessions_dir(), "**", "local_*.json"), recursive=True):
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            desktop[d["cliSessionId"]] = {"title": d.get("title"), "archived": bool(d.get("isArchived"))}
        except (OSError, ValueError, KeyError):
            pass

    days = defaultdict(lambda: {"messages": 0, "prompts": 0, "tools": 0, "sessions": set(),
                                "tokens": defaultdict(lambda: defaultdict(int))})
    hours = defaultdict(int)
    seen_msg = set()
    sessions = []

    for path in glob.glob(os.path.join(HOME, "projects", "**", "*.jsonl"), recursive=True):
        entries = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
        # The refresh task's prompt can arrive as a skill (isMeta), so look at every user row
        if any(e.get("type") == "user" and MARKER in prompt_text(e) for e in entries):
            continue

        title, last = None, None
        for e in entries:
            t = e.get("type")
            if t == "ai-title":
                title = e.get("aiTitle") or title
            if t not in ("user", "assistant") or not e.get("timestamp"):
                continue
            when = local(e["timestamp"])
            rec = days[when.date().isoformat()]
            rec["messages"] += 1
            if e.get("sessionId"):
                rec["sessions"].add(e["sessionId"])
            msg = e.get("message") or {}
            if t == "user" and is_prompt(e):
                rec["prompts"] += 1
                hours[when.hour] += 1
            if t == "assistant":
                content = msg.get("content")
                if isinstance(content, list):
                    rec["tools"] += sum(1 for c in content if isinstance(c, dict) and c.get("type") == "tool_use")
                # Streamed replies repeat one message id; count its usage once
                mid, u = msg.get("id"), msg.get("usage")
                if mid and u and msg.get("model", "").startswith("claude"):
                    if mid not in seen_msg:
                        seen_msg.add(mid)
                        for part, n in usage_parts(u).items():
                            rec["tokens"][msg["model"]][part] += n
                    if not e.get("isSidechain"):
                        last = (when, msg["model"], context_size(u), e.get("sessionId"), e.get("entrypoint"))

        if last:
            when, model, ctx, sid, entry = last
            meta = desktop.get(sid, {})
            recent = NOW - when <= timedelta(hours=ACTIVE_HOURS)
            open_in_app = sid in desktop and not meta.get("archived")
            if recent or open_in_app:
                window = context_window(model)
                sessions.append({
                    "session": sid,
                    "title": meta.get("title") or title,
                    "where": "desktop" if entry == "claude-desktop" or sid in desktop else "terminal",
                    "model": model,
                    "contextTokens": ctx,
                    "contextWindow": window,
                    "percentUsed": round(ctx / window * 100, 1) if window else None,
                    "lastActive": when.isoformat(timespec="minutes"),
                })

    # Claude Code deletes old transcripts; those days live on only in stats-cache.json
    cache = {}
    try:
        with open(os.path.join(HOME, "stats-cache.json"), encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        pass
    cache_act = {a["date"]: a for a in cache.get("dailyActivity", [])}
    cache_tok = {a["date"]: a["tokensByModel"] for a in cache.get("dailyModelTokens", [])}

    def estimate_parts(model, total):
        # The cache keeps only a day's total per model: split it by the model's all-time shares
        mu = cache.get("modelUsage", {}).get(model, {})
        shares = {
            "input": mu.get("inputTokens", 0),
            "cacheWrite5m": 0,
            "cacheWrite1h": mu.get("cacheCreationInputTokens", 0),  # Claude Code writes 1-hour cache
            "cacheRead": mu.get("cacheReadInputTokens", 0),
            "output": mu.get("outputTokens", 0),
        }
        whole = sum(shares.values())
        if not whole:
            return {**dict.fromkeys(PARTS, 0), "input": total}
        return {k: round(total * v / whole) for k, v in shares.items()}

    rows = []
    for d in sorted(set(days) | set(cache_act)):
        rec, c = days.get(d), cache_act.get(d, {})
        parts = {m: dict(p) for m, p in rec["tokens"].items()} if rec else {}
        is_estimated = False
        if sum(cache_tok.get(d, {}).values()) > sum(sum(p.values()) for p in parts.values()):
            parts = {m: estimate_parts(m, n) for m, n in cache_tok[d].items()}
            is_estimated = True
        by_model = {m: sum(p.values()) for m, p in parts.items()}
        costs = [cost_of(m, p) for m, p in parts.items()]

        def total(key):
            return sum(p.get(key, 0) for p in parts.values())

        rows.append({
            "date": d,
            "messages": max(rec["messages"] if rec else 0, c.get("messageCount", 0)),
            "prompts": rec["prompts"] if rec else None,
            "sessions": max(len(rec["sessions"]) if rec else 0, c.get("sessionCount", 0)),
            "tools": max(rec["tools"] if rec else 0, c.get("toolCallCount", 0)),
            "tokens": sum(by_model.values()),
            "topModel": max(by_model, key=by_model.get) if by_model else None,
            # All input the model read: uncached, cache writes and cache reads
            "inputTokens": total("input") + total("cacheWrite5m") + total("cacheWrite1h") + total("cacheRead"),
            "outputTokens": total("output"),
            "costUsd": round(sum(x for x in costs if x is not None), 4),
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
        "sessions": sorted(sessions, key=lambda s: s["lastActive"], reverse=True),
    }


def limits_from(out_dir):
    # usage_raw.json: the plan section of Claude Code's usage reading, left there by the web task
    path = os.path.join(out_dir, "usage_raw.json")
    try:
        with open(path, encoding="utf-8") as fh:
            plan = json.load(fh).get("plan", {})
    except (OSError, ValueError):
        return None
    fetched = datetime.fromtimestamp(os.path.getmtime(path)).astimezone().isoformat(timespec="minutes")
    return [{"limit": w.get("label"), "percentUsed": w.get("percentUsed"), "resetsAt": w.get("resetsAt"),
             "plan": plan.get("plan"), "fetchedAt": fetched} for w in plan.get("windows", [])]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print everything as one JSON object")
    ap.add_argument("--out", metavar="DIR", help="write the web dashboard's JSON files to DIR")
    args = ap.parse_args()
    if not args.json and not args.out:
        ap.error("pass --json or --out DIR")

    data = collect()
    if args.json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False))
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        files = {"daily.json": data["days"], "hours.json": data["hours"], "sessions.json": data["sessions"]}
        limits = limits_from(args.out)
        if limits is not None or not os.path.exists(os.path.join(args.out, "limits.json")):
            files["limits.json"] = limits or []
        for name, value in files.items():
            with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
                json.dump(value, fh, indent=1, ensure_ascii=False)
        if not args.json:
            print(f"{len(data['days'])} active days, {len(data['sessions'])} sessions -> {args.out}")


if __name__ == "__main__":
    main()
