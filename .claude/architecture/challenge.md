# Challenge JARVIS (Phase 48)

A counter-analysis of one finding, on demand. It looks for what would make the finding wrong; it
does not ask a model whether it is right.

## The steps (`backend/app/intelligence/challenge.py`)

1. **Counter-evidence**: every line of the run's documents, except the lines the finding cites, that
   shares at least half the claim's content words and disagrees with it: a date the claim's cannot
   be, a different figure, or a negation the claim lacks ("cancelled", "not", "postponed").
2. **Its own lines**: the temporal-consistency factor (Phase 46). A claim stating a date or figure
   its cited line does not hold is contested by its own citation.
3. **The negated claim, verified**: with a verifier (the API passes the configured one), the claim
   is checked against the counter lines alone. SUPPORTED dismisses them; anything else stands.
4. **Authority**: counter-evidence from a strictly more authoritative source (Phase 45 tiers) can
   overturn; from an equal or weaker one it contests.
5. **Confidence**: CONTESTED applies the disputed penalty; OVERTURNED the CONTRADICTED verdict cap.

| Outcome | When |
|---|---|
| WITHSTOOD | no counter-evidence and its own line holds it, or the verifier dismissed the counter lines |
| CONTESTED | counter-evidence no stronger than its own source, or its own line does not hold it |
| OVERTURNED | counter-evidence from a strictly more authoritative source, not dismissed |

The stored finding never changes: the challenge is kept beside it (`MissionRecord.challenges`),
with who asked and when, and before and after are both shown. Phase 50's review uses it.

## Where

- `POST /api/v1/missions/{id}/findings/{finding_id}/challenge` (actor from `X-Jarvis-User`),
  `GET /api/v1/missions/{id}/challenges`. The record keeps the documents' text for this.
- Console: "challenge this finding" in a finding's evidence panel on a live run.

## Measured: the challenge benchmark (`app/evaluation/challenge.py`)

Four documents of four authorities (approved plan, status report, vendor email, draft minutes),
six planted false findings and six true ones; deterministic, no model, re-run in CI
(`scripts/check_challenge_report.py`).

| Metric | Value |
|---|---|
| challenge_catch_rate | 0.833 (5 of 6 false findings not let stand) |
| challenge_false_alarm_rate | 0.000 (no true finding overturned) |

The miss is a wrong vendor name: no date, figure or negation to disagree on. Two true findings are
CONTESTED - a weaker source does disagree with them - which is right and is not a false alarm.

## Not built

Challenging HIGH and CRITICAL findings automatically before a report needs finding severity, which
arrives with the report rules in Phase 51.
