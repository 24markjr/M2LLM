# Benchmark 20261028T032721

Model: `qwen3:4b` · Same files and question to every system; scored against .agent/evals/benchmark/answers.yaml by a deterministic judge (no model grades any answer). correct = share of key facts stated; factscore = share of sentences supported by a line of the files (FActScore-style); invented = dates and figures in no file; citation precision = share of citations whose line is relevant to the claim (ALCE-style); false alarms on negative and injection scenarios.

| System | Correct | FActScore | Invented | Citation precision | False alarms | Latency |
|---|---|---|---|---|---|---|
| jarvis | 0.75 | 0.5 | 0 | 0.5 (4) | 0/1 | 162.4 s |
| plain | 1.0 | 0.462 | 0 | 1.0 (6) | 0/1 | 13.9 s |

Skipped: frontier models - none configured: set JARVIS_BENCH_FRONTIER (e.g. openai:gpt-4o) and its API key
