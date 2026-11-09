"""Synthetic BRI classification pilot: one model, six cases, no judge or live CI."""
import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from bri_pilot import CASES, SYSTEM_PROMPT, check_prediction, parse_prediction, pilot_summary, prompt_messages
from evidence_report import message_record, new_report, utc_now, write_report


def run(output_dir=None, *, model=None, root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    output_dir = Path(output_dir) if output_dir is not None else root / "results" / "bri-pilot"
    requested_model = os.getenv("CHAT_MODEL", "qwen3.5:4b")
    path, report = new_report(output_dir, root, requested_model)
    report["report_kind"] = "bri_synthetic_pilot"
    report["fixture_version"] = 1
    report["fixture_sha256"] = hashlib.sha256(
        json.dumps(CASES, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    report["system_prompt"] = SYSTEM_PROMPT
    report["pilot_source_sha256"] = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if (root / name).is_file() else None for name in ("bri_pilot.py", "eval_bri.py")
    }
    report["configuration"] = {
        "requested_model": requested_model, "temperature": 0, "reasoning": False,
        "num_predict": 512, "format": "json", "client_timeout_seconds": 120,
        "model_invoked": False, "agent_tools_bound": False, "judge_invoked": False,
        "live_ci_executed": False, "automatic_retries": 0,
        "expected_labels_sent_to_model": False,
        "data_kind": "authored_synthetic",
    }
    report["summary"] = pilot_summary([])
    write_report(path, report)
    print(f"SYNTHETIC BRI PILOT. No live CI or release action.\nReport: {path.resolve()}", flush=True)
    clock = perf_counter()
    code = 1
    try:
        if model is None:
            from langchain_ollama import ChatOllama
            model = ChatOllama(
                model=requested_model, temperature=0, reasoning=False,
                num_predict=512, format="json", client_kwargs={"timeout": 120.0},
            )
        for case in CASES:
            record = {
                **deepcopy(case), "status": "running", "prediction": None,
                "evaluation": None, "response": None, "error": None,
                "prompt_messages": prompt_messages(case),
                "started_at_utc": utc_now(), "finished_at_utc": None,
                "elapsed_seconds": None,
            }
            report["cases"].append(record)
            report["summary"] = pilot_summary(report["cases"])
            write_report(path, report)
            print(f"\nCASE {case['case_id']}: classifying...", flush=True)
            case_clock = perf_counter()
            try:
                report["configuration"]["model_invoked"] = True
                response = model.invoke(record["prompt_messages"])
                record["response"] = message_record(response)
                record["prediction"] = parse_prediction(response)
                record["evaluation"] = check_prediction(case, record["prediction"])
                record["status"] = "pass" if record["evaluation"]["passed"] else "fail"
                print(json.dumps(record["prediction"], ensure_ascii=False))
                print(f"Failures: {record['evaluation']['failures']}")
                print(f"CASE RESULT: {record['status'].upper()}", flush=True)
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                record["error"] = {"type": "KeyboardInterrupt", "message": "Case interrupted."}
                raise
            except Exception as error:
                record["status"] = "error"
                record["error"] = {"type": type(error).__name__, "message": str(error)}
                print(f"MODEL/OUTPUT ERROR: {type(error).__name__}: {error}", flush=True)
            finally:
                record["finished_at_utc"] = utc_now()
                record["elapsed_seconds"] = round(perf_counter() - case_clock, 6)
                report["summary"] = pilot_summary(report["cases"])
                write_report(path, report)
        report["run_status"] = "completed"
        code = 0 if report["summary"]["pass"] == len(CASES) else 1
    except KeyboardInterrupt:
        report["run_status"] = "interrupted"
        report["error"] = {"type": "KeyboardInterrupt", "message": "Run interrupted."}
        code = 130
    except Exception as error:
        report["run_status"] = "error"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"RUN ERROR: {type(error).__name__}: {error}", flush=True)
    finally:
        report["finished_at_utc"] = utc_now()
        report["elapsed_seconds"] = round(perf_counter() - clock, 6)
        report["summary"] = pilot_summary(report["cases"])
        write_report(path, report)
    print("\n" + json.dumps(report["summary"], indent=2))
    print(f"Run status: {report['run_status']}\nReport: {path.resolve()}", flush=True)
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    sys.exit(run(args.output_dir))
