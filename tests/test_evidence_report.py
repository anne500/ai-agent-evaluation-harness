"""JSON persistence and runner failure-path tests; no LangChain or Ollama."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as M
from unittest.mock import patch

from evidence_report import message_record, new_report, summarize, write_report
from eval_execution import PHRASE, run


CASES = [
    ("What time is it?", ":", "current_time", "Time"),
    ("Count words", "5", "word_count", "Count"),
    ("Capital?", "Paris", None, "Paris"),
    ("Count; avoid tools", None, "word_count", "Call tool"),
]


class FakeAgent:
    def __init__(self, behavior=None):
        self.index = 0
        self.behavior = behavior
        self.threads = []

    def invoke(self, state, config):
        self.index += 1
        self.threads.append(config["configurable"]["thread_id"])
        if self.behavior and self.index == 2:
            raise self.behavior
        name = CASES[self.index - 1][2]
        final = M(type="ai", content="Paris" if name is None else "5" if name == "word_count" else "Time: now",
                  tool_calls=[], response_metadata={"model": "fake", "done_reason": "stop"},
                  usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5})
        if name is None:
            return {"messages": [final]}
        value = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if name == "current_time" else "5"
        return {"messages": [
            M(type="ai", content="", tool_calls=[
                {"id": f"call-{self.index}", "name": name,
                 "args": {} if name == "current_time" else {"text": PHRASE}}
            ]),
            M(type="tool", content=value, name=name, tool_call_id=f"call-{self.index}", status="success"),
            final,
        ]}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke_runner(self, behavior=None):
        agent = FakeAgent(behavior)
        tutorial = M(CASES=CASES, build_agent=lambda: agent)
        with contextlib.redirect_stdout(io.StringIO()):
            code = run(self.root / "results", tutorial=tutorial, root=self.root)
        reports = list((self.root / "results").glob("*/report.json"))
        return code, json.loads(reports[-1].read_text(encoding="utf-8")), agent

    def test_unique_directories_do_not_replace_previous_run(self):
        first, doc = new_report(self.root, self.root, "fake")
        write_report(first, doc)
        second, _ = new_report(self.root, self.root, "fake")
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual(json.loads(first.read_text())["run_id"], doc["run_id"])

    def test_unicode_and_tool_ids_round_trip(self):
        path, doc = new_report(self.root, self.root, "fake")
        doc["cases"] = [{"text": "🧪 café", "tool_call_id": "call-9"}]
        write_report(path, doc)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["cases"], doc["cases"])

    def test_failed_serialization_preserves_previous_checkpoint(self):
        path, doc = new_report(self.root, self.root, "fake")
        write_report(path, doc)
        previous = path.read_bytes()
        doc["invalid"] = float("nan")
        with self.assertRaises(ValueError):
            write_report(path, doc)
        self.assertEqual(path.read_bytes(), previous)

    def test_failed_replace_preserves_previous_checkpoint(self):
        path, doc = new_report(self.root, self.root, "fake")
        write_report(path, doc)
        previous = path.read_bytes()
        with patch("evidence_report.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                write_report(path, {**doc, "run_status": "completed"})
        self.assertEqual(path.read_bytes(), previous)
        self.assertFalse(path.with_suffix(".tmp").exists())

    def test_message_metadata_and_arguments_are_preserved(self):
        msg = M(type="ai", content="5", tool_calls=[{"id": "c", "args": {"text": PHRASE}}],
                response_metadata={"done_reason": "length"}, usage_metadata={"output_tokens": 128},
                additional_kwargs={"reasoning_content": "not exported"})
        actual = message_record(msg)
        self.assertEqual(actual["response_metadata"]["done_reason"], "length")
        self.assertEqual(actual["usage_metadata"]["output_tokens"], 128)
        self.assertEqual(actual["tool_calls"][0]["args"]["text"], PHRASE)
        self.assertNotIn("additional_kwargs", actual)

    def test_complete_fake_run_records_four_cases_and_skipped_keyword(self):
        code, doc, agent = self.invoke_runner()
        self.assertEqual(code, 0)
        self.assertEqual(doc["run_status"], "completed")
        self.assertEqual(doc["summary"]["pass"], 4)
        self.assertEqual(doc["cases"][3]["keyword_status"], "skipped")
        self.assertEqual(len(set(agent.threads)), 4)
        self.assertTrue(all(c["invocation_finished_local"] for c in doc["cases"]))
        self.assertEqual(doc["cases"][1]["messages"][1]["tool_call_id"], "call-2")
        self.assertEqual(doc["cases"][1]["messages"][-1]["response_metadata"]["model"], "fake")
        self.assertIn("eval_execution.py", doc["provenance"]["source_sha256"])
        self.assertFalse(doc["configuration"]["judge_invoked"])

    def test_agent_error_is_recorded_and_later_cases_continue(self):
        code, doc, _ = self.invoke_runner(RuntimeError("synthetic invocation failure"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["pass"], 3)
        self.assertEqual(doc["summary"]["error"], 1)
        self.assertEqual(doc["cases"][1]["error"]["type"], "RuntimeError")
        self.assertIsNone(doc["cases"][1]["execution"])
        self.assertEqual(len(doc["cases"]), 4)

    def test_execution_failure_is_not_an_invocation_error(self):
        agent = FakeAgent()
        tutorial = M(CASES=CASES, build_agent=lambda: agent)
        with patch("eval_execution.check_execution", return_value={
            "passed": False, "failures": ["arguments"], "requested_tools": ["wrong"]
        }), contextlib.redirect_stdout(io.StringIO()):
            code = run(self.root / "results", tutorial=tutorial, root=self.root)
        path = next((self.root / "results").glob("*/report.json"))
        doc = json.loads(path.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["fail"], 4)
        self.assertEqual(doc["summary"]["error"], 0)

    def test_interrupt_retains_completed_and_interrupted_cases(self):
        code, doc, _ = self.invoke_runner(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertEqual(doc["run_status"], "interrupted")
        self.assertEqual(doc["summary"]["pass"], 1)
        self.assertEqual(doc["summary"]["interrupted"], 1)
        self.assertEqual(doc["summary"]["not_started"], 2)
        self.assertEqual(doc["cases"][1]["status"], "interrupted")

    def test_agent_construction_error_still_writes_report(self):
        def fail():
            raise RuntimeError("cannot construct agent")
        tutorial = M(CASES=CASES, build_agent=fail)
        with contextlib.redirect_stdout(io.StringIO()):
            code = run(self.root / "results", tutorial=tutorial, root=self.root)
        path = next((self.root / "results").glob("*/report.json"))
        doc = json.loads(path.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(doc["run_status"], "error")
        self.assertEqual(doc["summary"]["not_started"], 4)
        self.assertEqual(doc["error"]["type"], "RuntimeError")

    def test_summary_distinguishes_missing_cases_from_failed_cases(self):
        actual = summarize([{"status": "pass"}, {"status": "running"}], 4)
        self.assertEqual(actual["pass"], 1)
        self.assertEqual(actual["running"], 1)
        self.assertEqual(actual["not_started"], 2)
        self.assertEqual(actual["completed_cases"], 1)


if __name__ == "__main__":
    unittest.main()
