"""Calibrate a model judge on eight fixed labeled fixtures. No agent is run."""
import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from evidence_report import message_record, new_report, utc_now, write_report
from judge_calibration import CASES, SYSTEM_PROMPT, calibration_summary, parse_verdict, prompt_messages


def run(output_dir=None, *, judge=None, root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    output_dir = Path(output_dir) if output_dir is not None else root / "results" / "calibration"
    requested_model = os.getenv("JUDGE_MODEL", "qwen3.5:4b")
    path, report = new_report(output_dir, root, requested_model)
    report["report_kind"] = "judge_calibration"
    report["fixture_version"] = 1
    report["fixture_sha256"] = hashlib.sha256(
        json.dumps(CASES, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    report["judge_system_prompt"] = SYSTEM_PROMPT
    report["calibration_source_sha256"] = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if (root / name).is_file() else None
        for name in ("judge_calibration.py", "eval_calibration.py")
    }
    report["configuration"] = {
        "requested_judge_model": requested_model, "temperature": 0,
        "reasoning": False, "num_predict": 128, "client_timeout_seconds": 120,
        "agent_invoked": False, "judge_invoked": False,
        "automatic_retries": 0, "labels_sent_to_judge": False,
    }
    report["summary"] = calibration_summary([], len(CASES))
    write_report(path, report)
    print(f"Calibration report: {path.resolve()}", flush=True)
    clock = perf_counter()
    exit_code = 1
    try:
        if judge is None:
            from langchain_ollama import ChatOllama
            judge = ChatOllama(
                model=requested_model, temperature=0, reasoning=False,
                num_predict=128, client_kwargs={"timeout": 120.0},
            )
        for case in CASES:
            record = {
                **deepcopy(case), "status": "running", "verdict": None,
                "started_at_utc": utc_now(), "finished_at_utc": None,
                "elapsed_seconds": None, "response": None, "error": None,
                "prompt_messages": prompt_messages(case),
            }
            report["cases"].append(record)
            report["summary"] = calibration_summary(report["cases"], len(CASES))
            write_report(path, report)
            print(f"\nCASE {case['case_id']} ({case['category']}): judging...", flush=True)
            case_clock = perf_counter()
            try:
                report["configuration"]["judge_invoked"] = True
                response = judge.invoke(record["prompt_messages"])
                record["response"] = message_record(response)
                record["verdict"] = parse_verdict(response)
                record["status"] = "pass" if record["verdict"] == case["expected_label"] else "fail"
                print(
                    f"Expected={case['expected_label']} observed={record['verdict']} "
                    f"result={record['status'].upper()}", flush=True,
                )
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                record["error"] = {"type": "KeyboardInterrupt", "message": "Case interrupted."}
                raise
            except Exception as error:
                record["status"] = "error"
                record["error"] = {"type": type(error).__name__, "message": str(error)}
                print(f"JUDGE ERROR: {type(error).__name__}: {error}", flush=True)
            finally:
                record["finished_at_utc"] = utc_now()
                record["elapsed_seconds"] = round(perf_counter() - case_clock, 6)
                report["summary"] = calibration_summary(report["cases"], len(CASES))
                write_report(path, report)
        report["run_status"] = "completed"
        exit_code = 0 if report["summary"]["correct"] == len(CASES) else 1
    except KeyboardInterrupt:
        report["run_status"] = "interrupted"
        report["error"] = {"type": "KeyboardInterrupt", "message": "Run interrupted."}
        exit_code = 130
    except Exception as error:
        report["run_status"] = "error"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"RUN ERROR: {type(error).__name__}: {error}", flush=True)
    finally:
        report["finished_at_utc"] = utc_now()
        report["elapsed_seconds"] = round(perf_counter() - clock, 6)
        report["summary"] = calibration_summary(report["cases"], len(CASES))
        write_report(path, report)
    print("\n" + json.dumps(report["summary"], indent=2))
    print(f"Run status: {report['run_status']}")
    print(f"Calibration report: {path.resolve()}", flush=True)
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    sys.exit(run(args.output_dir))
