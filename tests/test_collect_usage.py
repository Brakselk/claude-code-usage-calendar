"""Tests for scripts/collect_usage.py, on made-up transcripts.  Run: python -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "collect_usage.py")
MARKER = "[usage-calendar-refresh]"


def row(kind, uuid, ts, session="s1", **extra):
    return {"type": kind, "uuid": uuid, "timestamp": ts, "sessionId": session, **extra}


def reply(uuid, ts, msg_id, session="s1", model="claude-opus-5-5", tools=0, usage=None, **extra):
    content = [{"type": "tool_use", "id": f"t{i}"} for i in range(tools)] or [{"type": "text", "text": "ok"}]
    usage = usage or {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 1000,
                      "cache_creation_input_tokens": 100, "cache_creation": {"ephemeral_1h_input_tokens": 100}}
    return row("assistant", uuid, ts, session, message={"id": msg_id, "model": model, "usage": usage, "content": content}, **extra)


def prompt(uuid, ts, text, session="s1", **extra):
    return row("user", uuid, ts, session, message={"role": "user", "content": text}, **extra)


def title(kind, text, session="s1"):
    field = {"ai-title": "aiTitle", "custom-title": "customTitle"}[kind]
    return {"type": kind, field: text, "sessionId": session}


def at(minute):
    """A time on 2026-10-20, a minute apart per step."""
    return f"2026-10-20T10:{minute:02d}:00Z"


def ago(minutes=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def strict_json(text):
    """JSON as JavaScript reads it: NaN and Infinity are not JSON."""
    def refuse(constant):
        raise ValueError(f"{constant} is not valid JSON")
    return json.loads(text, parse_constant=refuse)


class CollectUsage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "claude")
        self.projects = os.path.join(self.home, "projects", "p")
        os.makedirs(self.projects)
        self.env = {**os.environ, "CLAUDE_CONFIG_DIR": self.home, "TZ": "UTC0",
                    "APPDATA": os.path.join(self.tmp.name, "appdata"),
                    "LOCALAPPDATA": os.path.join(self.tmp.name, "local"),
                    "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "appdata"),
                    "HOME": self.tmp.name, "USERPROFILE": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def transcript(self, name, rows, raw_lines=()):
        path = os.path.join(self.projects, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            for line in raw_lines:
                fh.write(line + "\n")

    def stats_cache(self, activity=(), tokens=(), model_usage=None):
        with open(os.path.join(self.home, "stats-cache.json"), "w") as fh:
            json.dump({"dailyActivity": list(activity), "dailyModelTokens": list(tokens),
                       "modelUsage": model_usage or {}}, fh)

    def desktop_record(self, name, content):
        """A desktop app session file where this system's app keeps them; content may be any JSON value."""
        if sys.platform == "darwin":
            root = os.path.join(self.tmp.name, "Library", "Application Support", "Claude")
        else:
            root = os.path.join(self.env["APPDATA"], "Claude")  # XDG_CONFIG_HOME points there too
        folder = os.path.join(root, "claude-code-sessions", "a", "b")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            json.dump(content, fh)

    def run_script(self, *args, cp1254=False, env=None, cwd=None):
        if cp1254:
            # Not -I, which ignores PYTHONIOENCODING: this run really writes to a cp1254 pipe
            env = {k: v for k, v in (env or self.env).items() if not k.startswith("PYTHON")}
            env["PYTHONIOENCODING"] = "cp1254"  # a Windows pipe's code page: the script must not care
            cmd = [sys.executable, "-s", "-X", "utf8=0"]
            probe = subprocess.run(cmd + ["-c", "import sys; print(sys.stdout.encoding)"], env=env, capture_output=True)
            self.assertEqual(probe.stdout.decode("ascii").strip().lower(), "cp1254")
        else:
            cmd = [sys.executable, "-I"]
        return subprocess.run(cmd + [SCRIPT, *args], env=env or self.env, capture_output=True, cwd=cwd)

    def run_json(self, **kw):
        done = self.run_script("--json", **kw)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        return strict_json(done.stdout.decode("utf-8"))

    def day(self, data, date):
        return next(d for d in data["days"] if d["date"] == date)

    def titles(self, data):
        return {s["session"]: s["title"] for s in data["sessions"]}

    def test_rows_copied_into_another_file_count_once(self):
        rows = [prompt("u1", "2026-10-20T10:00:00Z", "hello"), reply("a1", "2026-10-20T10:00:05Z", "m1", tools=1)]
        self.transcript("s1.jsonl", rows)
        self.transcript("fork.jsonl", rows + [prompt("u2", "2026-10-20T11:00:00Z", "more", session="s2")])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["messages"], d["prompts"], d["tools"]), (3, 2, 1))
        self.assertEqual(d["tokens"], 1130)

    def test_streamed_copies_of_a_reply_count_once(self):
        self.transcript("s1.jsonl", [reply("a1", "2026-10-20T10:00:00Z", "m1"), reply("a2", "2026-10-20T10:00:01Z", "m1")])
        self.assertEqual(self.day(self.run_json(), "2026-10-20")["tokens"], 1130)

    def test_only_typed_prompts_count_as_prompts(self):
        self.transcript("s1.jsonl", [
            prompt("u1", "2026-10-20T10:00:00Z", "a real question"),
            prompt("u2", "2026-10-20T10:01:00Z", "<command-name>/model</command-name>"),
            prompt("u3", "2026-10-20T10:02:00Z", "<system-reminder>x</system-reminder>"),
            prompt("u4", "2026-10-20T10:03:00Z", "[Request interrupted by user]"),
            prompt("u5", "2026-10-20T10:04:00Z", "meta", isMeta=True),
            row("user", "u6", "2026-10-20T10:05:00Z", message={"content": [{"type": "tool_result", "content": "x"}]}),
        ])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual(d["prompts"], 1)
        self.assertEqual(d["messages"], 6)

    def test_typed_prompts_can_open_with_injected_blocks(self):
        human = {"origin": {"kind": "human"}}
        self.transcript("s1.jsonl", [
            # Newer Claude Code: origin says who wrote the row, whatever the text opens with
            prompt("u1", at(0), "<system-reminder>\nnote\n</system-reminder>\nmy question", **human),
            prompt("u2", at(1), '<artifact-view-context id="x">\nviewing\n</artifact-view-context>my question', **human),
            row("user", "u3", at(2), message={"content": [{"type": "text", "text": "<system-reminder>a</system-reminder>"},
                                                          {"type": "text", "text": "typed"}]}, **human),
            prompt("u4", at(3), "a plain-looking notification", origin={"kind": "task-notification"}),
            prompt("u5", at(4), "a message from another agent", origin={"kind": "peer"}),
            prompt("u6", at(5), "meta", isMeta=True, **human),
            row("user", "u7", at(6), message={"content": [{"type": "tool_result", "content": "x"}]}, **human),
            # Older Claude Code, no origin: told from the text past the injected blocks
            prompt("u8", at(7), "<system-reminder>x</system-reminder>\n  typed after a reminder"),
            prompt("u9", at(8), '<artifact-view-context a="1">x</artifact-view-context><system-reminder>y</system-reminder>typed'),
            prompt("u10", at(9), "<system-reminder>x</system-reminder><command-name>/model</command-name>"),
            prompt("u11", at(10), "<system-reminder>never closed, then text"),
        ])
        data = self.run_json()
        self.assertEqual(self.day(data, "2026-10-20")["prompts"], 5)  # u1, u2, u3, u8, u9
        self.assertEqual(sum(h["prompts"] for h in data["hours"]), 5)

    def test_compact_summaries_and_transcript_only_rows_are_not_prompts(self):
        self.transcript("s1.jsonl", [
            prompt("u1", at(0), "This session is being continued from a previous conversation", isCompactSummary=True),
            prompt("u2", at(1), "shown in the transcript only", isVisibleInTranscriptOnly=True),
            prompt("u3", at(2), "summary", isCompactSummary=True, origin={"kind": "human"}),
            prompt("u4", at(3), "a real question"),
        ])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["prompts"], d["messages"]), (1, 4))

    def test_refresh_task_sessions_and_their_subagents_are_left_out(self):
        self.transcript("task.jsonl", [prompt("u1", "2026-10-20T09:00:00Z", MARKER + "\nRefresh it", session="task"),
                                       reply("a1", "2026-10-20T09:00:05Z", "m1", session="task")])
        self.transcript("task/subagents/agent-1.jsonl", [reply("a2", "2026-10-20T09:01:00Z", "m2", session="task")])
        # A scheduled run wraps the prompt in a tag that opens a line
        self.transcript("run.jsonl", [prompt("u4", "2026-10-20T09:30:00Z",
                                             f'<scheduled-task name="refresh" file="x">\nautomated run\n{MARKER}\nRefresh it',
                                             session="run")])
        # Sessions that only talk about the marker or quote the wrapper stay in
        self.transcript("talk.jsonl", [prompt("u3", "2026-10-20T10:00:00Z", f"the task starts with {MARKER}", session="talk")])
        self.transcript("quote.jsonl", [prompt("u5", "2026-10-20T10:01:00Z",
                                               f'it matches `<scheduled-task name="x">` and {MARKER}', session="quote")])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["messages"], d["tokens"], d["sessions"]), (2, 0, 2))

    def test_marker_split_across_content_blocks_is_still_found(self):
        def blocks(*texts):
            return {"role": "user", "content": [{"type": "text", "text": t} for t in texts]}
        self.transcript("run1.jsonl", [row("user", "u1", at(0), "run1",
                                           message=blocks('<scheduled-task name="r">\nautomated run\n', MARKER + "\nRefresh it")),
                                       reply("a1", at(1), "m1", session="run1")])
        self.transcript("run2.jsonl", [row("user", "u2", at(2), "run2", message=blocks(MARKER, "Refresh it")),
                                       reply("a2", at(3), "m2", session="run2")])
        self.transcript("work.jsonl", [prompt("u3", at(4), "hello", session="work")])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["messages"], d["sessions"], d["tokens"]), (1, 1, 0))

    def test_marker_quoted_in_a_subagent_keeps_the_parent(self):
        self.transcript("work.jsonl", [prompt("u1", at(0), "hi", session="work"), reply("a1", at(1), "m1", session="work")])
        self.transcript("work/subagents/agent-1.jsonl", [
            prompt("u2", at(2), MARKER + " is what the task's prompt starts with", session="work", isSidechain=True),
            reply("a2", at(3), "m2", session="work", isSidechain=True)])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["prompts"], d["sessions"], d["messages"]), (1, 1, 4))

    def test_rows_after_copied_marker_rows_still_count(self):
        task = [prompt("u1", at(0), MARKER + "\nRefresh it", session="task"), reply("a1", at(1), "m1", session="task")]
        self.transcript("task.jsonl", task)
        self.transcript("fork.jsonl", task + [prompt("u2", at(2), "my own question", session="fork"),
                                              reply("a2", at(3), "m2", session="fork")])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["messages"], d["prompts"], d["sessions"], d["tokens"]), (2, 1, 1, 1130))

    def test_marker_after_a_byte_order_mark_is_found(self):
        self.transcript("task.jsonl", [prompt("u1", at(0), "﻿" + MARKER + "\nRefresh it", session="task"),
                                       reply("a1", at(1), "m1", session="task")])
        self.transcript("work.jsonl", [prompt("u2", at(2), "hello", session="work")])
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual((d["messages"], d["sessions"], d["tokens"]), (1, 1, 0))

    def test_transcript_days_ignore_the_caches_inflated_totals(self):
        self.transcript("s1.jsonl", [reply("a1", "2026-10-20T10:00:00Z", "m1")])
        self.stats_cache(
            activity=[{"date": "2026-10-20", "messageCount": 3, "sessionCount": 9, "toolCallCount": 9},
                      {"date": "2026-09-01", "messageCount": 6, "sessionCount": 1, "toolCallCount": 2}],
            tokens=[{"date": "2026-10-20", "tokensByModel": {"claude-opus-5-5": 2260}},
                    {"date": "2026-09-01", "tokensByModel": {"claude-opus-5-5": 1000}},
                    {"date": "2026-08-01", "tokensByModel": {"claude-opus-5-5": 500}}],
            model_usage={"claude-opus-5-5": {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": 7,
                                             "cacheCreationInputTokens": 1}})
        data = self.run_json()
        today = self.day(data, "2026-10-20")
        self.assertEqual((today["tokens"], today["messages"], today["isEstimated"], today["scaledFromCache"]),
                         (1130, 1, False, None))
        # The one overlapping day says the cache counts messages 3x and tokens 2x
        cached = self.day(data, "2026-09-01")
        self.assertEqual((cached["tokens"], cached["messages"], cached["isEstimated"], cached["prompts"]), (500, 2, True, None))
        self.assertEqual((cached["sessions"], cached["tools"]), (1, 2))
        self.assertEqual(self.day(data, "2026-08-01")["tokens"], 250)  # a day only in dailyModelTokens

    def test_cache_only_days_are_divided_by_the_median_overlap(self):
        for i, date in enumerate(("2026-10-18", "2026-10-19", "2026-10-20")):
            self.transcript(f"s{i}.jsonl", [reply(f"a{i}", f"{date}T10:00:00Z", f"m{i}", session=f"s{i}")])  # 1 message, 1130 tokens
        self.stats_cache(
            activity=[{"date": "2026-10-18", "messageCount": 2}, {"date": "2026-10-19", "messageCount": 3},
                      {"date": "2026-10-20", "messageCount": 10},
                      {"date": "2026-09-01", "messageCount": 30, "sessionCount": 4, "toolCallCount": 7}],
            tokens=[{"date": "2026-10-18", "tokensByModel": {"claude-opus-5-5": 2260}},
                    {"date": "2026-10-19", "tokensByModel": {"claude-opus-5-5": 2825}},
                    {"date": "2026-10-20", "tokensByModel": {"claude-opus-5-5": 10170}},
                    {"date": "2026-09-01", "tokensByModel": {"claude-opus-5-5": 5000}}])
        data = self.run_json()
        cached = self.day(data, "2026-09-01")
        self.assertEqual((cached["messages"], cached["tokens"], cached["sessions"], cached["tools"]), (10, 2000, 4, 7))
        self.assertEqual(cached["scaledFromCache"], {"messages": 3.0, "tokens": 2.5})
        self.assertTrue(cached["isEstimated"])
        self.assertEqual(self.day(data, "2026-10-19")["scaledFromCache"], None)

    def test_cache_only_days_stay_as_they_are_without_overlap(self):
        self.stats_cache(activity=[{"date": "2026-09-01", "messageCount": 30, "sessionCount": 4, "toolCallCount": 7}],
                         tokens=[{"date": "2026-09-01", "tokensByModel": {"claude-opus-5-5": 5000}}])
        cached = self.day(self.run_json(), "2026-09-01")
        self.assertEqual((cached["messages"], cached["tokens"], cached["scaledFromCache"]), (30, 5000, None))

    def test_cost_and_cache_write_split(self):
        usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 1000,
                 "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200}}
        self.transcript("s1.jsonl", [reply("a1", "2026-10-20T10:00:00Z", "m1", usage=usage),
                                     reply("a2", "2026-10-20T10:01:00Z", "m2", model="claude-mystery-9")])
        d = self.day(self.run_json(), "2026-10-20")
        # 100*4 + 100*5 + 200*8 + 1000*0.2 + 50*20 = 3700 per million
        self.assertAlmostEqual(d["costUsd"], 0.0037, places=6)
        self.assertEqual(d["unpricedTokens"], 1130)

    def test_bad_rows_and_files_are_skipped(self):
        os.makedirs(os.path.join(self.projects, "dir.jsonl"))
        self.transcript("s1.jsonl", [
            prompt("u1", "yesterday", "bad time"),
            row("assistant", "a1", "2026-10-20T10:00:00Z", message="not a dict"),
            row("assistant", "a2", "2026-10-20T10:00:01Z", message={"id": "m", "model": None, "usage": {}}),
            prompt("u2", "2026-10-20T10:00:02Z", "fine"),
        ], raw_lines=["null", "[1, 2]", "{not json", "[" * 100000])
        with open(os.path.join(self.home, "stats-cache.json"), "w") as fh:
            json.dump([1, 2, 3], fh)
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual(d["prompts"], 1)

    def test_odd_ids_and_half_emoji_titles_dont_crash(self):
        self.transcript("s1.jsonl", [
            row("user", ["a list"], at(0), message={"content": "uuid is a list"}),
            row("user", "u2", at(1), session={"a": "dict"}, message={"content": "sessionId is a dict"}),
            reply("a3", ago(), {"id": "a dict"}),
            {"type": "ai-title", "aiTitle": "cut \ud83d", "sessionId": "s1"},
        ])
        data = self.run_json()
        self.assertEqual(self.day(data, "2026-10-20")["prompts"], 2)
        self.assertEqual(self.titles(data), {"s1": "cut ?"})

    def test_out_of_range_timestamps_are_skipped(self):
        bad = ["1969-12-31T12:00:00Z", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z", "0001-01-01T00:00:00+05:00"]
        self.transcript("s1.jsonl", [prompt(f"u{i}", ts, "hi") for i, ts in enumerate(bad)] + [prompt("ok", at(0), "fine")])
        data = self.run_json()
        self.assertEqual([d["date"] for d in data["days"]], ["2026-10-20"])
        self.assertEqual(self.day(data, "2026-10-20")["prompts"], 1)

    def test_numbers_stay_valid_json(self):
        nan, inf = float("nan"), float("inf")
        usage = {"input_tokens": nan, "output_tokens": -5, "cache_read_input_tokens": inf, "cache_creation_input_tokens": 7}
        self.transcript("s1.jsonl", [reply("a1", at(0), "m1", usage=usage)])
        self.stats_cache(
            activity=[{"date": "2026-09-01", "messageCount": nan, "sessionCount": -3, "toolCallCount": inf}]
            + [{"date": bad, "messageCount": 1} for bad in ("2026-1-1", "20261001", "2026-10-01\n", "２０２６-０９-０２", "2026-02-30")],
            tokens=[{"date": "2026-09-01", "tokensByModel": {"claude-opus-5-5": inf, "claude-sonnet-5": 40}}],
            model_usage={"claude-sonnet-5": {"inputTokens": nan, "outputTokens": -1, "cacheReadInputTokens": 1}})
        data = self.run_json()  # parsed the way JavaScript would
        self.assertEqual([d["date"] for d in data["days"]], ["2026-09-01", "2026-10-20"])
        self.assertEqual(self.day(data, "2026-10-20")["tokens"], 7)
        cached = self.day(data, "2026-09-01")
        self.assertEqual((cached["messages"], cached["sessions"], cached["tools"], cached["tokens"]), (0, 0, 0, 40))
        # limits.json too: usage_raw.json comes from elsewhere
        out = os.path.join(self.tmp.name, "web")
        os.makedirs(out)
        with open(os.path.join(out, "usage_raw.json"), "w") as fh:
            json.dump({"plan": {"plan": ["odd"], "windows": [{"label": "5h", "percentUsed": nan, "resetsAt": inf}]}}, fh)
        self.assertEqual(self.run_script("--out", out).returncode, 0)
        with open(os.path.join(out, "limits.json"), encoding="utf-8") as fh:
            limits = strict_json(fh.read())
        self.assertEqual((limits[0]["limit"], limits[0]["percentUsed"], limits[0]["resetsAt"], limits[0]["plan"]),
                         ("5h", None, None, None))

    def test_titles_with_any_characters_come_through_as_utf8(self):
        self.desktop_record("local_x.json", {"cliSessionId": "s1", "title": "Çalışma → test 🚀", "isArchived": False})
        self.transcript("s1.jsonl", [reply("a1", ago(), "m1", entrypoint="claude-desktop")])
        data = self.run_json(cp1254=True)
        self.assertEqual(data["sessions"][0]["title"], "Çalışma → test 🚀")
        self.assertEqual(data["sessions"][0]["percentUsed"], 0.1)

    def test_desktop_files_that_are_not_objects_are_skipped(self):
        for i, junk in enumerate([[1, 2], None, "text", 5]):
            self.desktop_record(f"local_junk{i}.json", junk)
        self.desktop_record("local_s1.json", {"cliSessionId": "s1", "title": {"not": "a string"}})
        self.desktop_record("local_s2.json", {"cliSessionId": "s2", "title": "Kept"})
        self.transcript("s1.jsonl", [reply("a1", ago(1), "m1", session="s1")])
        self.transcript("s2.jsonl", [reply("a2", ago(2), "m2", session="s2")])
        self.assertEqual(self.titles(self.run_json()), {"s1": None, "s2": "Kept"})

    @unittest.skipUnless(sys.platform == "win32", "APPDATA and LOCALAPPDATA are read on Windows only")
    def test_unset_appdata_does_not_mean_the_current_folder(self):
        cwd = os.path.join(self.tmp.name, "cwd")
        for folder, sid in ((os.path.join("Claude", "claude-code-sessions", "a"), "s1"),
                            (os.path.join("Claude-Data", "inst", "claude-code-sessions"), "s2")):
            os.makedirs(os.path.join(cwd, folder))
            with open(os.path.join(cwd, folder, f"local_{sid}.json"), "w") as fh:
                json.dump({"cliSessionId": sid, "title": "from the current folder"}, fh)
        self.transcript("s1.jsonl", [reply("a1", ago(1), "m1", session="s1")])
        self.transcript("s2.jsonl", [reply("a2", ago(2), "m2", session="s2")])
        env = {k: v for k, v in self.env.items() if k != "LOCALAPPDATA"}
        env["APPDATA"] = ""
        self.assertEqual(self.titles(self.run_json(env=env, cwd=cwd)), {"s1": None, "s2": None})

    def test_latest_reply_wins_across_files_within_a_minute(self):
        base = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(second=0, microsecond=0)
        early, late = (base + timedelta(seconds=10)).isoformat(), (base + timedelta(seconds=30)).isoformat()
        small, big = {"input_tokens": 1}, {"input_tokens": 500}
        # Each file holds the later reply of one session, so the result can't depend on file order
        self.transcript("a.jsonl", [reply("x1", early, "mx1", session="x", usage=small),
                                    reply("y1", late, "my1", session="y", usage=big)])
        self.transcript("b.jsonl", [reply("x2", late, "mx2", session="x", usage=big),
                                    reply("y2", early, "my2", session="y", usage=small)])
        data = self.run_json()
        self.assertEqual({s["session"]: s["contextTokens"] for s in data["sessions"]}, {"x": 500, "y": 500})

    def test_titles_follow_their_session_across_files(self):
        self.transcript("p.jsonl", [title("ai-title", "Parent title", "p"), reply("p1", ago(10), "mp1", session="p")])
        # A fork carries copies of its parent's rows, an outdated title among them, then its own
        self.transcript("f.jsonl", [title("ai-title", "Old parent title", "p"), reply("p1", ago(10), "mp1", session="p"),
                                    prompt("f1", ago(9), "next", session="f"), title("ai-title", "Fork title", "f")])
        # A session's title row and its latest reply can sit in different files
        self.transcript("x.jsonl", [title("ai-title", "X title", "x"), reply("x1", ago(20), "mx1", session="x")])
        self.transcript("zz.jsonl", [reply("x2", ago(2), "mx2", session="x")])
        # A rename beats Claude's guess, before or after it; the desktop app's title beats both
        self.transcript("c.jsonl", [title("ai-title", "Guess", "c"), title("custom-title", "Renamed", "c"),
                                    title("ai-title", "Later guess", "c"), reply("c1", ago(3), "mc1", session="c")])
        self.desktop_record("local_d.json", {"cliSessionId": "d", "title": "App title"})
        self.transcript("d.jsonl", [title("custom-title", "Renamed d", "d"), reply("d1", ago(4), "md1", session="d")])
        self.assertEqual(self.titles(self.run_json()),
                         {"p": "Parent title", "x": "X title", "c": "Renamed", "d": "App title"})

    def test_empty_home_still_answers(self):
        data = self.run_json()
        self.assertEqual((data["days"], data["sessions"], len(data["hours"])), ([], [], 24))

    def test_out_expands_tilde(self):
        done = self.run_script("--out", "~/web", cwd=self.tmp.name)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "web", "daily.json")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "~")))

    def test_out_summary_survives_a_cp1254_pipe(self):
        target = os.path.join(self.tmp.name, "çıktı → web")  # "→" has no cp1254 byte
        done = self.run_script("--out", target, cp1254=True)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertIn(target, done.stdout.decode("utf-8"))
        self.assertTrue(os.path.exists(os.path.join(target, "daily.json")))

    def test_out_replaces_files_instead_of_rewriting_them(self):
        out = os.path.join(self.tmp.name, "web")
        self.assertEqual(self.run_script("--out", out).returncode, 0)
        # A second name for the same file shows whether it was rewritten in place or swapped for a new one
        daily, link = os.path.join(out, "daily.json"), os.path.join(self.tmp.name, "old-daily.json")
        try:
            os.link(daily, link)
        except OSError:
            self.skipTest("no hard links here")
        self.transcript("s1.jsonl", [prompt("u1", at(0), "hello")])
        self.assertEqual(self.run_script("--out", out).returncode, 0)
        with open(link, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), [])  # a reader holding the old file never sees a half-written one
        with open(daily, encoding="utf-8") as fh:
            self.assertEqual([d["date"] for d in json.load(fh)], ["2026-10-20"])
        self.assertEqual(sorted(os.listdir(out)), ["daily.json", "hours.json", "limits.json", "sessions.json"])

    def test_bad_out_folder_is_a_one_line_error(self):
        a_file = os.path.join(self.tmp.name, "a-file.txt")
        with open(a_file, "w") as fh:
            fh.write("x")
        for args in (["--out", ""], ["--json", "--out", ""], ["--out", a_file]):
            done = self.run_script(*args)
            err = done.stderr.decode("utf-8", "replace").strip()
            self.assertEqual(done.returncode, 2, args)
            self.assertEqual(len(err.splitlines()), 1, err)
            self.assertIn("--out", err)
            self.assertEqual(done.stdout, b"", args)  # checked before anything is collected or printed


if __name__ == "__main__":
    unittest.main()
