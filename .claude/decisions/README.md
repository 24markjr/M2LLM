# Architecture decisions

One file per decision. Numbered in the order taken.

## The numbering gap

**ADR-007 does not exist.** It was reserved for `ADR-007-cost-aware-policy.md` (Phase 17,
cost-aware planning policy). The policy was built - `app/intelligence/planning_policy/scoring.py`,
selected by `PLANNING_POLICY` - but the decision was never written up.

Recorded here rather than left as a gap, because a missing number reads as a lost file and sends a
reader looking for something that was never written.

| | Decision | Status |
|---|---|---|
| ADR-001 | Modular monolith, not microservices | Accepted |
| ADR-002 | PostgreSQL | Accepted |
| ADR-003 | Ollama for local inference | Accepted |
| ADR-004 | Custom orchestration, not an agent framework | Accepted |
| ADR-005 | pgvector for embeddings | Accepted |
| ADR-006 | Task graph as the execution model | Accepted |
| ADR-007 | *never written* - see above | - |
| ADR-008 | Server-sent events, not WebSocket | Accepted |
