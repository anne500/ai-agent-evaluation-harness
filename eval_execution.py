"""Execution validation with checkpointed JSON evidence. No LLM judge."""
import argparse
import importlib
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from evidence_report import message_record, new_report, summarize, utc_now, write_report
from execution_checks import ExecutionSpec, check_execution


PHRASE = "LangChain makes tool calling easier"
SPECS = [
    ExecutionSpec("current_time", {}, "time"),
    ExecutionSpec("word_count", {"text": PHRASE}, "count", 5),
    ExecutionSpec(None, {}, "none"),
    ExecutionSpec("word_count", {"text": PHRASE}, "count", 5),
]


def run(output_dir=None, *, tutorial=None, root=None):
    """Optional tutorial injection permits end-to-end offline failure tests."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    output_dir = Path(output_dir) if output_dir is not None else root / "results"
    path, evidence = new_report(
        output_dir, root, os.getenv("CHAT_MODEL", "qwen3.5:4b")
    )
    run_clock = perf_counter()
    write_report(path, evidence)
    print(f"Evidence report: {path.resolve()}", flush=True)
    exit_code = 1
    try:
        tutorial = tutorial if tutorial is not None else importlib.import_module("eval")
        if len(tutorial.CASES) != len(SPECS) or any(
            case[2] != spec.tool for case, spec in zip(tutorial.CASES, SPECS)
        ):
            raise ValueError("Tutorial cases changed; review execution specifications.")
        agent = tutorial.build_agent()
        for index, (case, spec) in enumerate(zip(tutorial.CASES, SPECS), 1):
            question, keyword, _, rubric = case
            print(f"\nCASE {index}: {question}", flush=True)
            record = {
                "case_id": index,
                "thread_id": f"execution-{uuid4().hex}",
                "question": question,
                "tutorial_judge_rubric": rubric,
                "expected_execution": asdict(spec),
                "keyword": keyword,
                "keyword_status": "not_evaluated",
                "status": "running",
                "started_at_utc": utc_now(),
                "finished_at_utc": None,
                "invocation_started_local": None,
                "invocation_finished_local": None,
                "elapsed_seconds": None,
                "answer": None,
                "messages": [],
                "execution": None,
                "error": None,
            }
            evidence["cases"].append(record)
            evidence["summary"] = summarize(evidence["cases"], len(SPECS))
            write_report(path, evidence)
            clock = perf_counter()
            try:
                started = datetime.now()
                record["invocation_started_local"] = started.isoformat()
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": question}]},
                    config={
                        "recursion_limit": 20,
                        "configurable": {"thread_id": record["thread_id"]},
                    },
                )
                finished = datetime.now()
                record["invocation_finished_local"] = finished.isoformat()
                messages = result["messages"]
                record["messages"] = [message_record(message) for message in messages]
                record["answer"] = messages[-1].content if messages else ""
                report = check_execution(messages, spec, started, finished)
                record["execution"] = report
                keyword_ok = keyword is None or (
                    isinstance(record["answer"], str)
                    and keyword.casefold() in record["answer"].casefold()
                )
                record["keyword_status"] = (
                    "skipped" if keyword is None else "pass" if keyword_ok else "fail"
                )
                record["status"] = "pass" if report["passed"] and keyword_ok else "fail"
                print(f"Answer: {record['answer']}")
                print(f"Requested tools: {report['requested_tools']}")
                print(f"Execution failures: {report['failures']}")
                print(f"Tutorial keyword check: {record['keyword_status']}")
                print(f"CASE RESULT: {record['status'].upper()}", flush=True)
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                record["error"] = {"type": "KeyboardInterrupt", "message": "User interrupted case."}
                raise
            except Exception as error:
                record["status"] = "error"
                record["error"] = {"type": type(error).__name__, "message": str(error)}
                print(f"AGENT/TRACE ERROR: {type(error).__name__}: {error}", flush=True)
            finally:
                record["finished_at_utc"] = utc_now()
                record["elapsed_seconds"] = round(perf_counter() - clock, 6)
                evidence["summary"] = summarize(evidence["cases"], len(SPECS))
                write_report(path, evidence)
        evidence["run_status"] = "completed"
        exit_code = 0 if all(c["status"] == "pass" for c in evidence["cases"]) else 1
    except KeyboardInterrupt:
        evidence["run_status"] = "interrupted"
        evidence["error"] = {"type": "KeyboardInterrupt", "message": "Run interrupted."}
        exit_code = 130
    except Exception as error:
        evidence["run_status"] = "error"
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"RUN ERROR: {type(error).__name__}: {error}", flush=True)
    finally:
        evidence["finished_at_utc"] = utc_now()
        evidence["elapsed_seconds"] = round(perf_counter() - run_clock, 6)
        evidence["summary"] = summarize(evidence["cases"], len(SPECS))
        write_report(path, evidence)

    summary = evidence["summary"]
    print(f"\nExecution + tutorial keyword passes: {summary['pass']}/{len(SPECS)}")
    print(f"Agent/trace errors: {summary['error']}")
    print(f"Run status: {evidence['run_status']}")
    print("LLM judge: not invoked in this extension run.")
    print(f"Evidence report: {path.resolve()}", flush=True)
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    sys.exit(run(args.output_dir))
