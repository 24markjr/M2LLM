# Scenarios

A scenario specifies **one complete agent behaviour** end to end: what the user asks, what
the agent has to work with, and what it must actually do about it.

Scenarios are how the six demos are proven — and how they stay proven as the system changes.

## What a scenario asserts

Crucially, a scenario does not just check the final answer. An agent can produce a
plausible-looking report while skipping every step that was supposed to make it
trustworthy. So scenarios assert against the **execution trace**: which events occurred, in
what order, and with what content.

## Schema

```yaml
id: evidence_gap
title: Agent identifies missing evidence and retrieves it
demo: 3                       # which demo this backs, if any
phase: 14                     # phase that makes this pass

objective: >
  Determine whether the project timeline is consistent with the approved baseline.

fixtures:
  documents:
    - fixtures/documents/project_report.pdf
    - fixtures/documents/milestone_report.pdf
  csv: []

# Optional fault injection — used by failed_tool.yaml and replanning.yaml.
inject:
  tool_failures:
    - tool: document_search
      fail_on_call: 1
      error: TIMEOUT

expect:
  # Intent
  intent:
    goal_contains: [timeline, baseline]
    required_operations_include: [extract_timeline, compare_sources]

  # Plan structure — edges, not exact task ids
  plan:
    min_tasks: 4
    must_depend:
      - [compare_dates, extract_timeline]

  # Trace assertions: the events that must appear, in order
  trace:
    must_contain_ordered:
      - EVIDENCE_GAP_DETECTED
      - REPLAN_STARTED
      - TASK_CREATED
      - TASK_COMPLETED
      - FINDING_VERIFIED
    must_not_contain:
      - RUN_FAILED

  # Findings
  findings:
    min_count: 1
    # Every finding must carry resolvable evidence. This is the project's
    # central claim; a scenario that does not check it is not testing JARVIS.
    all_have_resolved_evidence: true
    classifications_allowed: [FACT, INFERENCE, HYPOTHESIS]

  # Gap detection specifics
  evidence_gaps:
    min_count: 1
    types_include: [MISSING_BASELINE]
    # The gap must name a specific missing element, not say "more evidence".
    missing_element_is_specific: true

  # Bounds
  limits:
    max_replan_iterations: 3
    max_wallclock_s: 180
```

## Rules

1. **Assert behaviour, not prose.** Never assert on generated wording — it varies by model
   and by run, and asserting on it produces a brittle test that teaches nothing.
2. **Assert the trace.** The trace is the evidence that the agent did the work rather than
   guessed the answer.
3. **Negative scenarios are first-class.** `consistent_documents_no_contradiction` asserts
   that the agent finds *nothing*. An agent that always finds something is confabulating,
   and only a negative scenario catches it.
4. **Fixtures are deliberately flawed.** The contradictions, missing baselines and
   conflicting dates are planted. Their expected locations live in `fixtures/expected/`.

## Planned scenarios

| File | Behaviour | Demo | Phase |
|---|---|---|---|
| `basic_investigation.yaml` | Objective to result, with parallel execution | 1, 2 | 9 |
| `contradiction_detection.yaml` | Findings with evidence, classification, confidence | 6 | 13 |
| `evidence_gap.yaml` | Gap detected, named, and closed | 3 | 14 |
| `failed_tool.yaml` | Tool fails, retry, fallback, run completes | 4 | 11 |
| `replanning.yaml` | Plan invalidated, graph revised, execution continues | 5 | 16 |
| `complex_investigation.yaml` | Multi-document, multi-gap, several replans | — | 16 |
| `consistent_documents_no_contradiction.yaml` | Correctly finds nothing | — | 20 |
| `insufficient_evidence_unresolvable.yaml` | Stops honestly instead of promoting a guess | — | 20 |
