# Tutorial verification

Source: Darsh Shah, freeCodeCamp,
https://www.freecodecamp.org/news/how-to-evaluate-ai-agents-with-an-llm-as-a-judge-harness-in-python/

## Environment

Windows PowerShell, Python 3.14.4, pinned requirements.
Agent and judge: qwen3.5:4b.
Separate project: ai-agent-evaluation-harness.
Previous project checkpoint: 8be72c2.

## Recorded results

| Configuration | Deterministic passes | Judge YES | Judge errors |
| --- | --- | --- | --- |
| Basic prompt, answer-only judge | 3/4 | 3/4 | 0 |
| Stronger prompt, answer-only judge | 4/4 | 3/4 | 0 |
| Stronger prompt, tool evidence supplied | 4/4 | 3/4 | 1 |
| Stronger prompt, tool evidence, bounded judge | 4/4 | 3/4 | 0 |

All four runs reported zero agent errors.
These are individual runs, not repeated-run reliability estimates.

## Findings

The stronger prompt corrected the observed missing word_count request
in the case asking the agent to avoid tool use.

The trace-aware judge once returned empty content with done_reason=length.
A separate diagnostic reported 4,013 output tokens and about 537 seconds.

A diagnostic with reasoning=False and num_predict=128 returned NO,
done_reason=stop, and two output tokens. A subsequent full run completed
without judge errors.

Case 4's NO disagrees with the supplied required-tool request evidence.
The cause of this disagreement is unresolved.

## Evidence boundaries

Deterministic checks inspect answer keywords and requested tool names.
They do not validate arguments, execution success, or tool-result accuracy.
The fourth case skips its keyword check because its keyword is None.

Judge errors are unavailable evaluations, not NO verdicts.
Combined passes must be interpreted alongside separate results and errors.

## Tutorial adaptations

Separate summaries, strict verdict parsing, per-case error reporting,
tool-call evidence in judge input, and bounded judge generation.
The two-tool baseline has no checkpointer or persistent storage.

## Next extensions

- ✅ Execution extension verified separately: 15 Windows tests and 4/4 model-driven cases; see [Windows evidence](windows-execution-20261109.md).
- ✅ Structured JSON evidence verified: 26 Windows tests and an inspected 4/4 run; see [report audit](structured-evidence-verification-20261109.md).
- Calibrate the judge against known positive and negative examples.
- Add repeated runs and Build Release and Integration cases.
