# ADR-015 — Statement types are ruled from evidence; source authority informs and never decides

## Status

Accepted — 2026-10-11 (Phase 45, decision D18)

## Context

The v2 review saw every finding labelled FACT. JARVIS's `FindingClassification` already recomputed
FACT from what resolved, but it said FACT for a claim one document makes, and that is what the
review objected to: one source stating something makes it that source's claim, true to the source
and uncorroborated. The review also asked for source authority - an approved statement and a draft
email are not equal witnesses - without saying what authority should *do*.

## Decision

1. **A statement type per finding, ruled from its evidence** (`reasoning/statements.py`):
   UNKNOWN (nothing resolved), HYPOTHESIS (partly resolved), SOURCE_CLAIM (one document), FACT (two
   or more documents, every citation resolved, the claim supported or verified), INFERENCE (two or
   more documents with a step none states), CONTRADICTION (two different values, both cited and
   resolved, in a comparison or proposed as one). Set once the findings are final.
2. **The model proposes; the stricter answer wins.** Its `classification` is kept as `proposed_type`.
   A proposal can move a finding down the epistemic order, never up; RISK, RECOMMENDATION and
   OBSERVATION are kept only over a basis of FACT, SOURCE_CLAIM or INFERENCE, and the basis is stored
   beside them ("RISK on SOURCE_CLAIM").
3. **No single-source FACT, by the schema.** `Finding` refuses a FACT type or basis with fewer than two
   resolved documents.
4. **`FindingClassification` stays.** It caps confidence and is read by verification and memory; the
   statement type is what readers see. Two fields, one internal and one shown, rather than a change
   to the ruling every other component depends on.
5. **Authority is a tier per evidence item** (`.agent/config/authority.yaml`): set at intake by
   ordered name rules, changed by a person on the item's page (recorded as METADATA_CHANGED with the
   reason), items filed earlier assessed by the same rules and recorded so.
6. **Authority is reported, never used to settle a conflict.** A contradiction prints both sides'
   tiers. Nothing ranks, drops or rewrites a finding because one side is more official. Phase 46
   records the tier's weight as one factor of confidence, shown with its reason.

## Alternatives considered

- **Replace `FindingClassification` with the new types.** Touches the confidence ceiling, verification,
  memory distillation and every stored run, to rename what is already right internally.
- **Let authority resolve contradictions** (the approved figure wins). It is the reader's judgement, and
  the case the review cared about - an official document contradicted by a later draft - is exactly the
  one where the less official source may be the more current.
- **Authority from a model.** A model reading a file name and guessing its standing is a confident
  number with nothing behind it; ordered name rules are crude, visible and overridable.

## Consequences

- A broad question over one-document evidence now reads as SOURCE_CLAIMs, which is accurate and less
  impressive.
- Whether two agreeing documents produce one FACT or two SOURCE_CLAIMs depends on how the model cites;
  measured both ways on `vega_start_corroborated`. The guarantee is the downgrade, not the upgrade.
- The name rules are English and coarse ("report" is REPORT, "draft" wins over "approved"); a person
  corrects an item in one click, and the correction is in its custody.
