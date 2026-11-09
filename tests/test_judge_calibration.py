"""Judge calibration tests use fabricated verdicts only, no model calls."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as M

from eval_calibration import run
from judge_calibration import CASES, calibration_summary, parse_verdict, prompt_messages


def response(text, reason="stop"):
    return M(type="ai", content=text, tool_calls=[], response_metadata={"done_reason": reason},
             usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})


class FakeJudge:
    def __init__(self, replacement=None):
        self.index = 0
        self.replacement = replacement
        self.inputs = []

    def invoke(self, messages):
        index = self.index
        self.index += 1
        self.inputs.append(messages)
        if index == 1 and self.replacement is not None:
            if isinstance(self.replacement, BaseException):
                raise self.replacement
            return self.replacement
        return response(CASES[index]["expected_label"])


class CalibrationTests(unittest.TestCase):
    def test_fixtures_are_balanced_and_have_unique_ids(self):
        self.assertEqual(len(CASES), 8)
        self.assertEqual(len({c["case_id"] for c in CASES}), 8)
        self.assertEqual(sum(c["expected_label"] == "YES" for c in CASES), 4)
        self.assertEqual(sum(c["expected_label"] == "NO" for c in CASES), 4)
        self.assertTrue(all(c["label_rationale"] for c in CASES))

    def test_expected_labels_are_not_in_model_input(self):
        case = {**CASES[0], "expected_label": "SECRET-LABEL", "label_rationale": "SECRET-RATIONALE"}
        serialized = json.dumps(prompt_messages(case))
        self.assertNotIn("SECRET-LABEL", serialized)
        self.assertNotIn("SECRET-RATIONALE", serialized)
        self.assertEqual(json.loads(prompt_messages(case)[1]["content"]), case["evidence"])

    def test_claimed_tool_without_trace_is_negative(self):
        case = next(c for c in CASES if c["case_id"] == "requested_no")
        self.assertIn("I used word_count", case["evidence"]["answer"])
        self.assertEqual(case["evidence"]["tool_calls"], [])
        self.assertEqual(case["expected_label"], "NO")

    def test_conflicting_user_request_with_actual_trace_is_positive(self):
        case = next(c for c in CASES if c["case_id"] == "requested_yes")
        self.assertIn("Avoid tool use", case["evidence"]["question"])
        self.assertEqual(case["evidence"]["tool_calls"][0]["name"], "word_count")
        self.assertEqual(case["expected_label"], "YES")

    def test_parse_verdict_allows_case_and_outer_whitespace_only(self):
        self.assertEqual(parse_verdict(response(" yes\n")), "YES")
        self.assertEqual(parse_verdict(response("NO")), "NO")

    def test_empty_explanation_and_nontext_verdicts_are_errors(self):
        for value in ("", "YES because it does", "NO.", None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_verdict(response(value))

    def test_truncated_yes_is_error(self):
        with self.assertRaises(ValueError):
            parse_verdict(response("YES", "length"))

    def test_unexpected_tool_call_is_error(self):
        item = response("YES")
        item.tool_calls = [{"name": "word_count"}]
        with self.assertRaises(ValueError):
            parse_verdict(item)

    def test_matrix_and_error_denominators(self):
        rows = [
            {"category": "a", "expected_label": "YES", "verdict": "YES", "status": "pass"},
            {"category": "a", "expected_label": "YES", "verdict": "NO", "status": "fail"},
            {"category": "b", "expected_label": "NO", "verdict": "YES", "status": "fail"},
            {"category": "b", "expected_label": "NO", "verdict": "NO", "status": "pass"},
            {"category": "a", "expected_label": "YES", "verdict": None, "status": "error"},
        ]
        result = calibration_summary(rows, 8)
        self.assertEqual(result["confusion_matrix_valid_only"], {
            "true_positive": 1, "false_negative": 1, "false_positive": 1, "true_negative": 1
        })
        self.assertEqual(result["agreement_on_valid"], 0.5)
        self.assertEqual(result["valid_coverage"], 0.5)
        self.assertEqual(result["correct_over_all_cases"], 0.25)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["not_started"], 3)

    def test_no_valid_verdicts_has_null_agreement(self):
        self.assertIsNone(calibration_summary([], 8)["agreement_on_valid"])

    def execute(self, replacement=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        judge = FakeJudge(replacement)
        with contextlib.redirect_stdout(io.StringIO()):
            code = run(Path(temp.name) / "results", judge=judge, root=Path(temp.name))
        path = next(Path(temp.name).glob("results/*/report.json"))
        return code, json.loads(path.read_text(encoding="utf-8")), judge

    def test_all_correct_fake_judge_records_eight_successes(self):
        code, doc, judge = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(doc["summary"]["correct"], 8)
        self.assertEqual(doc["run_status"], "completed")
        self.assertEqual(len(judge.inputs), 8)
        self.assertFalse(doc["configuration"]["labels_sent_to_judge"])
        self.assertFalse(doc["configuration"]["agent_invoked"])
        self.assertEqual(doc["cases"][0]["response"]["usage_metadata"]["output_tokens"], 2)
        self.assertEqual(len(doc["fixture_sha256"]), 64)

    def test_disagreement_is_not_an_error(self):
        code, doc, _ = self.execute(response("YES"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["disagreements"], 1)
        self.assertEqual(doc["summary"]["errors"], 0)

    def test_truncation_preserves_raw_response_and_continues(self):
        code, doc, _ = self.execute(response("YES", "length"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["errors"], 1)
        self.assertEqual(doc["cases"][1]["response"]["content"], "YES")
        self.assertIsNone(doc["cases"][1]["verdict"])
        self.assertEqual(len(doc["cases"]), 8)

    def test_invocation_failure_is_recorded(self):
        code, doc, _ = self.execute(RuntimeError("synthetic connection failure"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["errors"], 1)
        self.assertEqual(doc["cases"][1]["error"]["type"], "RuntimeError")
        self.assertIsNone(doc["cases"][1]["response"])

    def test_interrupt_preserves_partial_report(self):
        code, doc, _ = self.execute(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertEqual(doc["run_status"], "interrupted")
        self.assertEqual(doc["summary"]["correct"], 1)
        self.assertEqual(doc["summary"]["interrupted"], 1)
        self.assertEqual(doc["summary"]["not_started"], 6)


if __name__ == "__main__":
    unittest.main()
