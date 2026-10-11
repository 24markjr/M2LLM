# ADR-016 — Review decisions and the audit log are append-only; the audit is structural

## Status

Accepted — 2026-10-11 (Phase 50)

## Context

The v2 review asked for human review of findings and an audit log of every action. Two failure modes
matter: a decision quietly changed after the fact (who approved this, and when?), and a write path
that forgets to log itself (the audit is only as complete as its least careful route).

## Decision

1. **A decision is a record, never an edit.** Approving after rejecting adds a decision; both stay.
   `review_decisions` is append-only by a database trigger, as custody is (ADR-014).
2. **The audit log is append-only too**, by the same trigger function.
3. **Every write is audited by middleware, not by each route.** A route cannot be added unaudited;
   refused writes are recorded as well, because an attempt is part of the record. A test calls every
   write route in the OpenAPI schema and checks each left an entry.
4. **Review gates memory.** A finding the rules say needs a person contributes no fact until approved;
   when the rules cannot be evaluated, everything is held.
5. **Rules in YAML**, each with the reason shown to the reviewer; none is a model's judgement.

## Alternatives considered

- **A `state` column on findings, updated in place.** Simple, and loses who changed what and why.
- **Audit calls in each route.** Richer details per route, and one forgotten call away from a gap;
  the system's own actions are audited explicitly on top of the middleware.

## Consequences

- The audit log grows with every write, including refused ones; nothing prunes it, by design.
- Actor identity is the `X-Jarvis-User` header until authentication (Phase 55) makes it a verified
  user; the log records what was claimed, and Phase 55 makes the claim mean something.
