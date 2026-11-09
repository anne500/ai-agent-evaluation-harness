"""Tutorial cases with separate rule and judge summaries."""
import os

from langchain_ollama import ChatOllama

from agent import build_agent


CASES = [
    (
        "What time is it right now?",
        ":", "current_time",
        "The answer includes a specific time.",
    ),
    (
        'How many words are in: "LangChain makes tool calling easier"',
        "5", "word_count",
        "The answer clearly gives a word count of 5.",
    ),
    (
        "What is the capital of France?",
        "Paris", None,
        "The answer identifies Paris.",
    ),
    (
        "How many words are in 'LangChain makes tool calling easier'? Avoid tool use",
        None, "word_count",
        "The assistant calls the word_count tool.",
    ),
]


def run():
    agent = build_agent()
    judge = ChatOllama(
        model=os.getenv("JUDGE_MODEL", "qwen3.5:4b"),
        temperature=0,
    )
    rules_passed = judge_yes = combined_passed = 0
    agent_errors = judge_errors = 0

    for number, (question, keyword, expected_tool, rubric) in enumerate(CASES, 1):
        print(f"\nCASE {number}: {question}", flush=True)

        try:
            state = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config={"recursion_limit": 20},
            )
            answer = state["messages"][-1].content
            if not isinstance(answer, str):
                raise TypeError("Expected a text answer.")

            calls = [
                call["name"]
                for message in state["messages"]
                for call in (getattr(message, "tool_calls", None) or [])
            ]
        except Exception as error:
            agent_errors += 1
            print(f"AGENT ERROR: {type(error).__name__}: {error}")
            continue

        keyword_ok = keyword is None or keyword.casefold() in answer.casefold()
        tool_ok = expected_tool in calls if expected_tool else not calls
        rules_ok = keyword_ok and tool_ok
        rules_passed += int(rules_ok)

        print(f"Answer: {answer}")
        print(f"Requested tools: {calls}")
        print(f"Rules: keyword={keyword_ok}, tool={tool_ok}")

        try:
            verdict = judge.invoke(
                f"Question: {question}\nAnswer: {answer}\n"
                f"Recorded tool-call requests: {calls}\n"
                f"Rubric: {rubric}\n"
                "Does the answer satisfy the rubric? Respond only YES or NO."
            ).content.strip().upper()

            if verdict not in {"YES", "NO"}:
                raise ValueError(f"Invalid judge response: {verdict!r}")
        except Exception as error:
            judge_errors += 1
            print(f"JUDGE ERROR: {type(error).__name__}: {error}")
            continue

        judge_ok = verdict == "YES"
        judge_yes += int(judge_ok)
        combined_passed += int(rules_ok and judge_ok)
        print(f"Judge: {verdict}")

    total = len(CASES)
    print(f"\nDeterministic passes: {rules_passed}/{total}")
    print(f"Judge YES:           {judge_yes}/{total}")
    print(f"Combined passes:     {combined_passed}/{total}")
    print(f"Agent errors: {agent_errors}; judge errors: {judge_errors}")


if __name__ == "__main__":
    run()
