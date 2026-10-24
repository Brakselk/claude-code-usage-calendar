"""Tests for scripts/collect_usage.py, on made-up transcripts.  Run: python -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

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
                    "HOME": self.tmp.name, "USERPROFILE": self.tmp.name,
                    "PYTHONIOENCODING": "cp1254"}  # a Windows pipe's code page: the script must not care

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

    def run_json(self):
        done = subprocess.run([sys.executable, "-I", SCRIPT, "--json"], env=self.env, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        return json.loads(done.stdout.decode("utf-8"))

    def day(self, data, date):
        return next(d for d in data["days"] if d["date"] == date)

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

    def test_transcript_days_ignore_the_caches_inflated_totals(self):
        self.transcript("s1.jsonl", [reply("a1", "2026-10-20T10:00:00Z", "m1")])
        with open(os.path.join(self.home, "stats-cache.json"), "w") as fh:
            json.dump({
                "dailyActivity": [{"date": "2026-10-20", "messageCount": 99, "sessionCount": 9, "toolCallCount": 9},
                                  {"date": "2026-09-01", "messageCount": 5, "sessionCount": 1, "toolCallCount": 2}],
                "dailyModelTokens": [{"date": "2026-10-20", "tokensByModel": {"claude-opus-5-5": 999999}},
                                     {"date": "2026-09-01", "tokensByModel": {"claude-opus-5-5": 1000}},
                                     {"date": "2026-08-01", "tokensByModel": {"claude-opus-5-5": 500}}],
                "modelUsage": {"claude-opus-5-5": {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": 7,
                                                   "cacheCreationInputTokens": 1}},
            }, fh)
        data = self.run_json()
        today = self.day(data, "2026-10-20")
        self.assertEqual((today["tokens"], today["messages"], today["isEstimated"]), (1130, 1, False))
        cached = self.day(data, "2026-09-01")
        self.assertEqual((cached["tokens"], cached["messages"], cached["isEstimated"], cached["prompts"]), (1000, 5, True, None))
        self.assertEqual(self.day(data, "2026-08-01")["tokens"], 500)  # a day only in dailyModelTokens

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
        ], raw_lines=["null", "[1, 2]", "{not json"])
        with open(os.path.join(self.home, "stats-cache.json"), "w") as fh:
            json.dump([1, 2, 3], fh)
        d = self.day(self.run_json(), "2026-10-20")
        self.assertEqual(d["prompts"], 1)

    def test_titles_with_any_characters_come_through_as_utf8(self):
        sessions = os.path.join(self.env["APPDATA"], "Claude", "claude-code-sessions", "a", "b")
        os.makedirs(sessions)
        with open(os.path.join(sessions, "local_x.json"), "w", encoding="utf-8") as fh:
            json.dump({"cliSessionId": "s1", "title": "Çalışma → test 🚀", "isArchived": False}, fh)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        self.transcript("s1.jsonl", [reply("a1", now, "m1", entrypoint="claude-desktop")])
        data = self.run_json()
        self.assertEqual(data["sessions"][0]["title"], "Çalışma → test 🚀")
        self.assertEqual(data["sessions"][0]["percentUsed"], 0.1)

    def test_empty_home_still_answers(self):
        data = self.run_json()
        self.assertEqual((data["days"], data["sessions"], len(data["hours"])), ([], [], 24))

    def test_out_expands_tilde(self):
        done = subprocess.run([sys.executable, "-I", SCRIPT, "--out", "~/web"], env=self.env, capture_output=True,
                              cwd=self.tmp.name)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "web", "daily.json")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "~")))


if __name__ == "__main__":
    unittest.main()
