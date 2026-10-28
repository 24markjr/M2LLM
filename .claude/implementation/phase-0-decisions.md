# Phase 0 - decisions and setup (v4 product plan)

Started 2026-10-26. The record of what was decided and set up before any build phase, so nothing
here has to be reconstructed from memory.

## 1. Cloud (GCP) - set up

| Item | Value |
|---|---|
| Google account | `chackomartin123@gmail.com` (only this account; no Arcaisys account is used for Tessera) |
| Local CLI profile | `gcloud` configuration **`tessera`** - use `CLOUDSDK_ACTIVE_CONFIG_NAME=tessera` or `--configuration=tessera`. The machine's `default` profile is someone else's and is never touched |
| Project | **Tessera**, ID **`tessera-jarvis`** (number 430202798261) |
| Billing | Free-trial billing account `0117F5-77E787-CE1EB0`, ₹28,797 credit, expires 25 Jan 2027 |
| Budget guard | "Tessera monthly guard": ₹5,000 / month on this project, alerts at 50 %, 90 %, 100 % |
| Region / zone | `asia-south1` (Mumbai) / `asia-south1-a` - data stays in India (DPDP Act) |
| APIs enabled | Compute, Cloud SQL Admin, Cloud Storage, Secret Manager, Identity Toolkit (Identity Platform), Artifact Registry, Cloud KMS, Logging, Monitoring, Billing Budgets, Resource Manager |
| Planned layout | One L4 (24 GB) VM running the containers and the model server; Cloud SQL for PostgreSQL with pgvector; Cloud Storage with KMS keys for evidence; Secret Manager; Identity Platform for login. GKE later |

### Blocker: GPU quota

`NVIDIA_L4_GPUS` in `asia-south1` is 1, but **`GPUS_ALL_REGIONS` is 0**: a free-trial account cannot
attach GPUs. To unblock (owner's decision - it is a billing change):

1. Console > Billing > **Upgrade** to a paid account. The remaining credit is kept and is spent first.
2. Console > IAM & Admin > Quotas: request `GPUS_ALL_REGIONS` = 1 (and confirm `NVIDIA_L4_GPUS` in
   `asia-south1` = 1).

Until then Phase 1 can be built and tested on CPU-only VMs and Cloud SQL; the model server waits.

## 2. Indian languages - decided

Open-source AI4Bharat models are the primary engine (Phase 6); the Bhashini API is an optional second
engine (Phase 7). **Bhashini application: to be submitted by the owner** (it needs the applicant's
own identity and organisation) - status: *not yet submitted*.

## 3. Licence register

Every model or library that ships, with its licence, checked before commercial use. "Verify" means
the licence must be confirmed from the model card before launch; the entry is not a legal opinion.

| Component | Used for | Licence | Commercial use |
|---|---|---|---|
| qwen3:4b (Qwen3) | Reasoning, planning, synthesis | Apache-2.0 | Yes |
| Larger Qwen3 (14B/32B, Phase 2 candidate) | Reasoning on the cloud GPU | Apache-2.0 | Yes |
| nomic-embed-text | Embeddings (pgvector) | Apache-2.0 | Yes |
| **qwen2.5vl:3b** (Qwen2.5-VL-3B) | Describing images and video frames | **Qwen Research License** | **No - replace before launch** (candidate: Qwen2.5-VL-7B, Apache-2.0 - verify) |
| Whisper weights via faster-whisper | Speech-to-text | MIT | Yes |
| RapidOCR (PaddleOCR models) | OCR | Apache-2.0 | Yes |
| python-evtx | Windows `.evtx` logs | Apache-2.0 | Yes (verify) |
| Neo4j Community | Knowledge graph store | GPL-3.0 | Yes as an unmodified separate server; do not link into proprietary code |
| PostgreSQL + pgvector | Database | PostgreSQL licence | Yes |
| docling (optional) | PDF layout | MIT | Yes (verify) |
| pyannote speaker-diarization (optional) | Who spoke when | MIT, gated model (accept terms) | Yes (verify) |
| IndicTrans2 distilled 200M, both directions (Phase 6) - CTranslate2 conversions `adalat-ai/ct2-rotary-indictrans2-{indic-en,en-indic}-dist-200M` @ `524aade4f724` / `ee04de9a86e4` | Indian-language translation | MIT (model cards) | Yes |
| SentencePiece | IndicTrans2's tokenizer | Apache-2.0 | Yes |
| AI4Bharat speech / OCR models (Phase 6) | Indian-language ASR / OCR | Per model | **Verify each before use** |
| NLLB-200 | (rejected) | CC-BY-NC-4.0 | **No - not to be used** |

## 4. Pinned model versions (as running on 2026-10-26)

| Model | Ollama digest |
|---|---|
| qwen3:4b | `359d7dd4bcda` |
| nomic-embed-text:latest | `0a109f422b47` |
| qwen2.5vl:3b | `fb90415cde1e` (to be replaced) |
| faster-whisper | `base` (CPU, int8) |

Phase 1 moves these pins into deployment configuration; a model change becomes a recorded,
benchmarked change rather than whatever `latest` resolves to.

## 5. Data routing policy (by sensitivity)

Uses the sensitivity selector the composer already has. Enforced from Phase 1 (storage) and Phase 7
(language engines).

| Sensitivity | Processed by | May leave our GCP project? |
|---|---|---|
| Restricted | Our models only, in `tessera-jarvis` | Never |
| Confidential | Our models only, in `tessera-jarvis` | Never |
| Internal | Our models; Bhashini allowed for language tasks | Only to Bhashini, only for language tasks |
| Unclassified | Our models; Bhashini allowed | Only to Bhashini |

- A customer organisation can tighten its policy (e.g. no Bhashini at all); it can never loosen it.
- Frontier cloud models (the B1 benchmark option) are for synthetic benchmark fixtures only - never
  customer evidence.
- Every receipt records which engine processed what, so the routing can be audited after the fact.

## 6. Status

| Item | Status |
|---|---|
| GCP project, billing, region, APIs, budget guard | Done |
| GPU quota | **Blocked** - needs the paid-account upgrade and a quota request (owner) |
| Bhashini application | **Owner to submit** |
| Licence register | Done; one launch blocker found (qwen2.5vl:3b) |
| Pinned versions | Recorded |
| Routing policy | Written |
