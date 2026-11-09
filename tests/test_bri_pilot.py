"""Synthetic BRI checks and fake-model persistence, without Ollama."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as M

from bri_pilot import CASES, check_prediction, parse_prediction, pilot_summary, prompt_messages
from eval_bri import run


def expected_prediction(case):
    expected = case["expected"]
    return {
        "failure_category": expected["failure_category"],
        "release_decision": expected["release_decision"],
        "evidence_ids": expected["required_evidence_ids"].copy(),
    }


def response(prediction, reason="stop"):
    return M(type="ai", content=json.dumps(prediction), tool_calls=[],
             response_metadata={"done_reason": reason}, usage_metadata={"output_tokens": 20})


class FakeModel:
    def __init__(self, replacement=None):
        self.index = 0
        self.replacement = replacement

    def invoke(self, messages):
        index = self.index
        self.index += 1
        if index == 1 and self.replacement is not None:
            if isinstance(self.replacement, BaseException):
                raise self.replacement
            return self.replacement
        return response(expected_prediction(CASES[index]))


class BriPilotTests(unittest.TestCase):
    def test_six_unique_synthetic_cases(self):
        self.assertEqual(len(CASES), 6)
        self.assertEqual(len({c["case_id"] for c in CASES}), 6)
        self.assertTrue(all(c["data_kind"] == "authored_synthetic" for c in CASES))

    def test_expected_labels_never_enter_prompt(self):
        case = {**CASES[0], "expected": {"secret": "HIDDEN-LABEL"}, "label_rationale": "HIDDEN-REASON"}
        text = json.dumps(prompt_messages(case))
        self.assertNotIn("HIDDEN-LABEL", text)
        self.assertNotIn("HIDDEN-REASON", text)
        self.assertEqual(json.loads(prompt_messages(case)[1]["content"]), case["evidence"])

    def test_expected_predictions_pass_all_fixtures(self):
        for case in CASES:
            with self.subTest(case=case["case_id"]):
                p = parse_prediction(response(expected_prediction(case)))
                self.assertTrue(check_prediction(case, p)["passed"])

    def test_missing_and_stale_evidence_require_review(self):
        for case in CASES[-2:]:
            with self.subTest(case=case["case_id"]):
                p = {**expected_prediction(case), "release_decision": "ready"}
                self.assertIn("release_decision", check_prediction(case, p)["failures"])

    def test_wrong_category_fails_even_if_blocking(self):
        p = {**expected_prediction(CASES[0]), "failure_category": "test_assertion"}
        self.assertIn("failure_category", check_prediction(CASES[0], p)["failures"])

    def test_invented_citation_fails(self):
        p = {**expected_prediction(CASES[0]), "evidence_ids": ["integration.detail", "invented"]}
        self.assertIn("citation_ids_exist", check_prediction(CASES[0], p)["failures"])

    def test_missing_required_citation_fails(self):
        p = {**expected_prediction(CASES[0]), "evidence_ids": []}
        self.assertIn("required_citations_present", check_prediction(CASES[0], p)["failures"])

    def test_green_case_requires_all_status_citations(self):
        p = expected_prediction(CASES[3])
        p["evidence_ids"].pop()
        self.assertFalse(check_prediction(CASES[3], p)["passed"])

    def test_truncation_rejects_valid_looking_json(self):
        with self.assertRaises(ValueError):
            parse_prediction(response(expected_prediction(CASES[0]), "length"))

    def test_bad_schema_types_extra_keys_and_unknown_values_fail(self):
        base = expected_prediction(CASES[0])
        invalid = [
            [], {**base, "extra": 1}, {**base, "failure_category": []},
            {**base, "failure_category": "made_up"}, {**base, "release_decision": "ship"},
            {**base, "evidence_ids": "integration.detail"},
            {**base, "evidence_ids": [1]},
            {**base, "evidence_ids": ["integration.detail", "integration.detail"]},
        ]
        for p in invalid:
            with self.subTest(prediction=p), self.assertRaises(ValueError):
                parse_prediction(response(p))

    def test_duplicate_json_keys_fail(self):
        item = response({})
        item.content = '{"failure_category":"none","failure_category":"none","release_decision":"ready","evidence_ids":[]}'
        with self.assertRaises(ValueError):
            parse_prediction(item)

    def test_unexpected_tool_call_fails(self):
        item = response(expected_prediction(CASES[0]))
        item.tool_calls = [{"name": "shell"}]
        with self.assertRaises(ValueError):
            parse_prediction(item)

    def execute(self, replacement=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with contextlib.redirect_stdout(io.StringIO()):
            code = run(Path(temp.name) / "results", model=FakeModel(replacement), root=Path(temp.name))
        path = next(Path(temp.name).glob("results/*/report.json"))
        return code, json.loads(path.read_text())

    def test_complete_fake_run_persists_six_cases(self):
        code, doc = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(doc["summary"]["pass"], 6)
        self.assertEqual(doc["report_kind"], "bri_synthetic_pilot")
        self.assertFalse(doc["configuration"]["live_ci_executed"])
        self.assertFalse(doc["configuration"]["judge_invoked"])
        self.assertEqual(len(doc["fixture_sha256"]), 64)
        self.assertEqual(doc["cases"][1]["response"]["usage_metadata"]["output_tokens"], 20)

    def test_disagreement_is_not_output_error(self):
        p = {**expected_prediction(CASES[1]), "release_decision": "ready"}
        code, doc = self.execute(response(p))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["fail"], 1)
        self.assertEqual(doc["summary"]["error"], 0)

    def test_invalid_json_is_error_and_response_is_retained(self):
        item = response({})
        item.content = "not JSON"
        code, doc = self.execute(item)
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["error"], 1)
        self.assertEqual(doc["cases"][1]["response"]["content"], "not JSON")

    def test_invocation_error_is_recorded_and_later_cases_continue(self):
        code, doc = self.execute(RuntimeError("synthetic model failure"))
        self.assertEqual(code, 1)
        self.assertEqual(doc["summary"]["error"], 1)
        self.assertEqual(doc["summary"]["pass"], 5)

    def test_interrupt_retains_partial_run(self):
        code, doc = self.execute(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertEqual(doc["run_status"], "interrupted")
        self.assertEqual(doc["summary"]["pass"], 1)
        self.assertEqual(doc["summary"]["not_started"], 4)


if __name__ == "__main__":
    unittest.main()
