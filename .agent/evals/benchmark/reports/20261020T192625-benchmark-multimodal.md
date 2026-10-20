# Benchmark 20261020T192625

Model: `qwen3:4b` · Same files and question to every system; scored against .agent/evals/benchmark/answers.yaml by a deterministic judge (no model grades any answer). correct = share of key facts stated; factscore = share of sentences supported by a line of the files (FActScore-style); invented = dates and figures in no file; citation precision = share of citations whose line is relevant to the claim (ALCE-style); false alarms on negative and injection scenarios.

| System | Correct | FActScore | Invented | Citation precision | False alarms | Latency |
|---|---|---|---|---|---|---|
| jarvis | 0.375 | 0.667 | 0 | 1.0 (4) | 0/1 | 60.6 s |
| plain | 1.0 | 0.6 | 0 | 0.8 (5) | 0/1 | 4.5 s |

Skipped: frontier models - none configured: set JARVIS_BENCH_FRONTIER (e.g. openai:gpt-4o) and its API key
