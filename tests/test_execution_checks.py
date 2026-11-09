"""Adversarial synthetic traces for execution validation, without model calls."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace as Message

from execution_checks import ExecutionSpec, check_execution


PHRASE = "LangChain makes tool calling easier"


class ExecutionChecksTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 9, 12, 0, 0, 500000)
        self.end = self.start + timedelta(seconds=3)
        self.spec = ExecutionSpec("word_count", {"text": PHRASE}, "count", 5)

    def trace(self):
        return [
            Message(type="ai", tool_calls=[
                {"id": "call-1", "name": "word_count", "args": {"text": PHRASE}}
            ]),
            Message(type="tool", tool_call_id="call-1", name="word_count",
                    content="5", status="success"),
            Message(type="ai", content="There are 5 words.", tool_calls=[]),
        ]

    def check(self, trace, spec=None):
        return check_execution(trace, spec or self.spec, self.start, self.end)

    def test_valid_count_execution(self):
        self.assertTrue(self.check(self.trace())["passed"])

    def test_correct_answer_without_execution_fails(self):
        self.assertFalse(self.check(self.trace()[-1:])["passed"])

    def test_wrong_text_even_with_same_count_fails(self):
        trace = self.trace()
        trace[0].tool_calls[0]["args"] = {"text": "one two three four five"}
        self.assertIn("arguments", self.check(trace)["failures"])

    def test_missing_result_fails(self):
        trace = self.trace()
        del trace[1]
        self.assertIn("result_pairing", self.check(trace)["failures"])

    def test_wrong_result_id_fails(self):
        trace = self.trace()
        trace[1].tool_call_id = "unrelated"
        self.assertIn("result_pairing", self.check(trace)["failures"])

    def test_result_before_call_fails(self):
        trace = self.trace()
        trace[0], trace[1] = trace[1], trace[0]
        self.assertIn("result_pairing", self.check(trace)["failures"])

    def test_error_status_with_plausible_value_fails(self):
        trace = self.trace()
        trace[1].status = "error"
        self.assertIn("execution_status", self.check(trace)["failures"])

    def test_wrong_or_non_numeric_result_fails(self):
        for value in ["4", "15", "error: 5", "5.0"]:
            with self.subTest(value=value):
                trace = self.trace()
                trace[1].content = value
                self.assertIn("result_value", self.check(trace)["failures"])

    def test_extra_tool_call_fails(self):
        trace = self.trace()
        trace[0].tool_calls.append(
            {"id": "extra", "name": "current_time", "args": {}}
        )
        self.assertIn("call_count", self.check(trace)["failures"])
        self.assertIn("tool_name", self.check(trace)["failures"])

    def test_duplicate_results_fail(self):
        trace = self.trace()
        trace.insert(2, trace[1])
        self.assertIn("result_pairing", self.check(trace)["failures"])

    def test_invalid_tool_call_fails(self):
        trace = self.trace()
        trace[0].invalid_tool_calls = [{"name": "word_count", "args": "bad json"}]
        self.assertIn("parseable_calls", self.check(trace)["failures"])

    def test_blank_or_pending_final_answer_fails(self):
        for final in [
            Message(type="ai", content="", tool_calls=[]),
            Message(type="ai", content="pending", tool_calls=[{"id": "pending"}]),
        ]:
            with self.subTest(final=final):
                trace = self.trace()
                trace[-1] = final
                self.assertIn("final_answer", self.check(trace)["failures"])

    def test_no_tool_case_rejects_orphan_result(self):
        spec = ExecutionSpec(None, {}, "none")
        self.assertTrue(self.check(self.trace()[-1:], spec)["passed"])
        self.assertFalse(self.check(self.trace()[1:], spec)["passed"])

    def test_valid_time_with_second_precision(self):
        trace = self.trace()
        trace[0].tool_calls[0].update(name="current_time", args={})
        trace[1].name = "current_time"
        trace[1].content = "2026-11-09 12:00:00"
        self.assertTrue(self.check(
            trace, ExecutionSpec("current_time", {}, "time")
        )["passed"])

    def test_stale_future_or_invalid_time_fails(self):
        for value in [
            "2026-11-08 12:00:00",
            "2026-11-09 12:00:10",
            "2026-02-30 12:00:00",
            "no time available",
        ]:
            with self.subTest(value=value):
                trace = self.trace()
                trace[0].tool_calls[0].update(name="current_time", args={})
                trace[1].name = "current_time"
                trace[1].content = value
                self.assertIn("result_value", self.check(
                    trace, ExecutionSpec("current_time", {}, "time")
                )["failures"])


if __name__ == "__main__":
    unittest.main()
