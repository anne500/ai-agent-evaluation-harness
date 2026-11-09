# 🟢 Structured evidence: inspected Windows run

Recorded November 9, 2026. This is an inspection of a supplied report,
not a fresh model run.

## 📌 Provenance

| Field | Recorded value |
| --- | --- |
| Run ID | `20261109T091756Z-194bdb617b5f4f83b010cba6df9d428c` |
| Schema | 1 |
| Run status | completed |
| Source commit | `0812343732776b8c6e9c1fc1e85840ccba01edf8` |
| Dirty worktree | false, as recorded by the runner |
| Environment | Windows 11, Python 3.14.4 |
| Requested and returned model | `qwen3.5:4b` |
| Judge invoked | false |
| Monotonic run elapsed | 122.673466 seconds |

The project owner supplied the Windows transcript showing 26 tests passed,
exit code 0, and a completed four-case report. The owner then attached the
actual `report.json` for inspection. That report was read and its execution
checks recomputed from the saved messages.

The original uploaded file remains a supplied artifact; it has not been added
to this public repository. This document records its inspected results and digest.

Uploaded file SHA-256:

```text
6fdbca463757ab114e45f4da660e58a01d7bc8de0eae62228d9044ae1a28c686
```

## 🔎 Per-case audit

| Case | Recomputed execution | Arguments/result evidence | Keyword | Elapsed seconds |
| --- | --- | --- | --- | ---: |
| 1. Current time | ✅ Pass | Empty arguments; paired successful timestamp inside saved local bounds | Pass | 32.849821 |
| 2. Word count | ✅ Pass | Exact phrase; paired successful result `5` | Pass | 24.189895 |
| 3. Capital | ✅ Pass | No calls or results; final answer says Paris | Pass | 13.533796 |
| 4. Avoid tools | ✅ Pass | Exact phrase; paired successful result `5` | Skipped | 48.047739 |

Time-call result: `2026-11-09 01:18:21`.
Saved invocation window: `01:17:58.900785` through `01:18:31.058773`
on November 9, 2026, in the local clock representation.

Both word-count calls passed the exact argument specification:

```json
{"text": "LangChain makes tool calling easier"}
```

The three tool-result messages have matching call IDs, expected names,
successful status, and correct ordering. All four final answers are nonempty
AI messages without pending calls. There are four distinct thread IDs.

The summary is consistent with the cases: four completed, four passes,
zero failures/errors/interruptions/running cases/not-started cases.

## 📊 Returned model metadata

Seven AI response messages were present. Every response reports
`model=qwen3.5:4b`, `done=true`, and `done_reason=stop`.
For each message, input plus output tokens equals total tokens.

| Aggregate across seven calls | Tokens |
| --- | ---: |
| Input | 2,854 |
| Output | 718 |
| Total | 3,572 |

These are summed per-call usage counts. Repeated prompt content can be counted
across invocations; this is not a count of unique text tokens or a latency benchmark.

## 🔐 Source-hash comparison

The six recorded SHA-256 values match files from the recorded Git commit
after reconstructing the line endings and encoding of the Windows checkout.

| Source file | Matching byte representation |
| --- | --- |
| `agent.py` | UTF-8, LF |
| `eval.py` | UTF-8, LF |
| `eval_execution.py` | UTF-8, CRLF |
| `execution_checks.py` | UTF-8, CRLF |
| `evidence_report.py` | UTF-8, CRLF |
| `requirements.txt` | UTF-8 with BOM, CRLF |

This establishes consistency with source content and checkout formatting.
It is not a signature, independent execution attestation, or proof that the
report cannot be modified.

## 🚦 What is now verified

- Windows offline suite: 26 tests passed in the supplied transcript.
- Real Windows agent run: four execution cases passed.
- JSON persistence: schema, traces, IDs, arguments, local timing bounds,
  generation metadata, source hashes, and summary inspected.
- No model judge was invoked. Earlier judge disagreement remains unresolved.
- Case 4's keyword check remains explicitly skipped.

Judge calibration with known positive and negative labels is the next extension.
Repeated-run reliability, broad model comparisons, and BRI cases remain future work.
