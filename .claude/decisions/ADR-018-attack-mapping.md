# ADR-018 — ATT&CK is vendored from the official bundle; techniques are mapped by rule

## Status

Accepted — 2026-10-12 (Phase 53, decision D14)

## Context

A cyber investigation names the adversary's techniques in MITRE ATT&CK terms. The names and ids must
be real, the mapping must say why it was made, and an inferred step of an attack must never pass for
an observed one.

## Decision

1. **The catalogue is the official Enterprise ATT&CK STIX bundle, pinned to v15.1**, reduced by a
   script to the live techniques' id, name, tactics and URL, stamped with the bundle's SHA-256, and
   kept in the repository so the mapping works offline. The 26 MB bundle itself is not committed.
2. **Techniques are mapped by declared rules**, never by a model: each names its technique, the event
   fields, and in words why. A rule cannot name a technique the catalogue lacks.
3. **Every mapping needs an analyst**: marked so, and a finding citing a mapped event needs review.
4. **Observed and inferred edges are different kinds**, stored, served and drawn apart; an inferred
   edge carries its reason.
5. **Precision and recall are measured** on fixtures with ground truth, one of them written after the
   rules, and re-checked in CI.

## Alternatives considered

- **A model assigning techniques**: plausible ids with no trace of why; would need its own labelled
  source and validation, and is deferred.
- **Sigma rules**: the established format, and a large dependency and translation layer for twelve
  rules; worth adopting when the rule set grows.

## Consequences

- Recall is limited to what has a rule: 0.400 on the held-out fixture.
- Updating ATT&CK means downloading a new pinned bundle and re-running the script; rules naming
  retired techniques then fail to load, which is the point.
