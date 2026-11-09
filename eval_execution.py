"""Extension 1: execution evidence, using the tutorial cases. No LLM judge."""
import importlib
import json
import sys
from datetime import datetime
from uuid import uuid4

from execution_checks import ExecutionSpec, check_execution


PHRASE = "LangChain makes tool calling easier"
SPECS = [
    ExecutionSpec("current_time", {}, "time"),
    ExecutionSpec("word_count", {"text": PHRASE}, "count", 5),
    ExecutionSpec(None, {}, "none"),
    ExecutionSpec("word_count", {"text": PHRASE}, "count", 5),
]


def run():
    tutorial = importlib.import_module("eval")
    if len(tutorial.CASES) != len(SPECS):
        raise ValueError("Tutorial cases changed; review execution specifications.")
    agent = tutorial.build_agent()
    passed = errors = 0
    for index, (case, spec) in enumerate(zip(tutorial.CASES, SPECS), 1):
        question, keyword, _, _ = case
        print(f"\nCASE {index}: {question}", flush=True)
        started = datetime.now()
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config={
                    "recursion_limit": 20,
                    "configurable": {"thread_id": f"execution-{uuid4().hex}"},
                },
            )
            finished = datetime.now()
            messages = result["messages"]
            report = check_execution(messages, spec, started, finished)
            answer = messages[-1].content if messages else ""
            keyword_ok = keyword is None or (
                isinstance(answer, str) and keyword.casefold() in answer.casefold()
            )
            case_ok = report["passed"] and keyword_ok
            passed += int(case_ok)
            print(f"Answer: {answer}")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"Tutorial keyword check: {keyword_ok}")
            print(f"CASE RESULT: {'PASS' if case_ok else 'FAIL'}")
        except Exception as error:
            errors += 1
            print(f"AGENT/TRACE ERROR: {type(error).__name__}: {error}", flush=True)

    print(f"\nExecution + tutorial keyword passes: {passed}/{len(SPECS)}")
    print(f"Agent/trace errors: {errors}")
    print("LLM judge: not invoked in this extension run.")
    return 0 if passed == len(SPECS) and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
