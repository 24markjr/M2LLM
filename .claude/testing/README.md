# Testing

Three layers, testing three different things. Confusing them is how a project ends up with
high coverage and no confidence.

| Layer | Location | Question |
|---|---|---|
| Unit | `backend/tests/unit/` | Does this function or state machine work? |
| Integration | `backend/tests/integration/` | Do the components work together, against a real database? |
| Agent | `.agent/tests/`, `.agent/scenarios/` | Does the *agent* behave correctly? |
| Evaluation | `.agent/evals/` | How well does it behave, measured? |

| Document | Covers | Phase |
|---|---|---|
| `testing-strategy.md` | The three layers, what belongs where, determinism | 23 |
| `unit-tests.md` | Conventions, fixtures, what to mock | 23 |
| `integration-tests.md` | Database fixtures, test DB lifecycle | 23 |
| `agent-evaluation.md` | The harness, metrics, ground truth | 20 |
| `regression-testing.md` | Baselines, tolerances, unexplained improvements | 20 |

## Why the agent layer exists separately

A unit test can prove `TaskGraph.ready_tasks()` never returns a task with an incomplete
ancestor. It cannot prove that when evidence is insufficient, the agent identifies what is
missing and goes and gets it. That behaviour emerges from six components interacting, and
only an end-to-end scenario asserting against the execution trace can catch it breaking.

Scenarios assert on the **trace**, not on generated prose. An agent can produce a
plausible-looking report while skipping every step that was supposed to make it
trustworthy — asserting on the output would not notice; asserting on the trace does.

## Determinism

The suite must be runnable without a model:

- `LLM_PROVIDER=echo` serves recorded fixture responses. CI runs the full suite with no
  network, no GPU and no secrets.
- Temperature 0 and a fixed seed for real-model runs.
- `pytest-randomly` shuffles test order, because agent state is exactly the kind of thing
  that grows accidental ordering dependencies.

## Adversarial suite

Every component gets hostile cases, because these are what separate a system from a demo:

- Prompt injection inside uploaded documents — document content is data, never instruction
- Malformed plans: cycles, dangling dependencies, empty task lists
- Contradictory sources with no tiebreak available
- Empty, corrupt and oversized documents
- Runs that legitimately produce zero findings
- Tool timeout storms

## Invariant tests

Each "must not do" from the specification has a test that fails if it is violated:

| Invariant | Test |
|---|---|
| The LLM is reached only through `app/llm/` | `test_llm_isolation.py` |
| No `eval`/`exec` anywhere | ruff `S` rules + calculator AST whitelist test |
| No model deliberation in persisted events | redaction test on the event sink |
| Every adaptive loop is bounded | `test_config.py::test_every_loop_has_a_ceiling` |
| No hard-coded evaluation numbers | scorers take runs as input; report generation is a pure function |

The last one is the most important and the hardest to test directly. The structural defence
is that reports are generated files produced from persisted runs, and are never edited.
