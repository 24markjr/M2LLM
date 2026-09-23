# Integrations

Contracts with the other members' services. Written in Phase 2 and frozen there, so that
Member 1's build order never depends on anyone else's.

| Document | Service | Protocol | Phase |
|---|---|---|---|
| `m2context.md` | Member 2 — context store | `ContextProvider` | 12 |
| `member-3-knowledge.md` | Member 3 — knowledge base | `KnowledgeProvider` | 12 |
| `member-4-verification.md` | Member 4 — verification | `VerificationProvider` | 15 |

## The rule

> Never import another member's implementation directly.

Each service is reached through a protocol in `app/integrations/`, selected by environment
variable, with a timeout and a documented degradation path. Nothing else in the codebase
knows a remote service exists.

## Local fallbacks

Every protocol has a working local implementation, and they are not throwaway stubs:

| Protocol | Fallback | What it actually does |
|---|---|---|
| `ContextProvider` | pgvector retrieval | Real semantic search over ingested chunks, with source locators |
| `KnowledgeProvider` | Local document index | Search across the run's document set |
| `VerificationProvider` | `BaselineVerifier` | A genuine independent check — sees the claim and evidence, never the reasoning trail |

This means the full evidence-and-verification story holds even if no remote service ever
arrives. If one does, it swaps in at a single seam.

## What each contract document must specify

1. The protocol signature
2. Request and response schemas, with examples
3. Timeout and retry behaviour
4. **The degradation path** — what happens when the service is unavailable, and what gets
   recorded. Degradation is never silent: a remote verifier timing out records
   `VERIFICATION_DEGRADED`, because a finding that looks verified and is not is worse than
   one honestly marked unverified.
5. The local fallback's behaviour and its known differences from the remote service
