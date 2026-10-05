# ADR-012 — Seeing and hearing: read, seen and heard, kept apart

## Status

Accepted — 2026-10-05 (Phase 39)

## Context

Phase 38 accepted images and video and could say only their size. The owner's requirement for
Phase 39: *"our AI needs to understand not only text but also the content itself"* - what a photo
shows, what a chart says, what a scanned page reads, what is said in a recording.

The system's core rule is that every claim is bound to evidence it can cite. A model that looks at a
photo and writes a description produces text that was not in any source: if that text were treated
like a document's own words, a model's guess could become a "supported" finding and, through the
knowledge layer, a contradiction. Member 2's design deferred vision (`vision/` raised
`NotImplementedError`); D8 had recommended OCR only, for this reason.

## Decision

**Three engines, all local, and their outputs kept apart by what they are.**

| | Engine | Output | Weight |
|---|---|---|---|
| **Read** | OCR: PaddleOCR's models through RapidOCR (ONNX) | the text in images, scanned PDF pages, video frames, as lines | evidence, like any document text; low-confidence lines marked |
| **Heard** | Speech-to-text: faster-whisper (`base`, CPU, int8) | what is said in video and audio, one timed segment per line | evidence; a person's transcript (`.srt`/`.vtt`) is preferred when present |
| **Seen** | A vision model through Ollama: `qwen2.5vl:3b`, the `vision` role in `models.yaml`, reached through `app/llm/` | `[seen]` lines: what an image or frame shows, specific observations, what is unclear | **an account, not evidence of the same weight** |

**`[seen]` is one marker, read by every layer** (`schemas.evidence.SEEN_MARKER`):

- the knowledge layer never grounds a value on a `[seen]` line, so a vision model's description can
  never create a contradiction (`extraction.ground`);
- after any verifier, a finding whose resolved evidence is **only** `[seen]` lines cannot be
  `SUPPORTED`: it becomes `PARTIALLY_SUPPORTED` with a `DESCRIBED_ONLY` issue, which is actionable,
  so the loop can look for something read that confirms it (`verification.described_only`);
- the reasoning model reads the marker on every such line.

**Understanding runs once per file and is cached** by SHA-256 in `.agent/media-cache/` (ignored by
git). It runs on upload, and before a mission, an analysis, a CLI investigation or an evaluation
scenario reads a file not yet understood (`formats.prepare`). Parsing reads the cache and makes no
model call, so the loader stays fast and synchronous.

## Why these engines

- **RapidOCR over PaddleOCR itself:** the same PaddleOCR models, without PaddlePaddle's large install;
  a pip wheel with the models included. Measured: a line of printed text read at 0.997 confidence,
  first call about 3 s.
- **`qwen2.5vl:3b`:** strong on documents, charts and photos for its size; 3.2 GB beside `qwen3:4b`
  on a 6 GB GPU. Swappable with `VISION_MODEL`, which, like `OLLAMA_MODEL`, wins over the YAML - and
  only for the vision role, so swapping the text model for an experiment never swaps the eyes.
- **faster-whisper on the CPU:** local, no model service, and off the GPU Ollama is using. Its audio
  is decoded by our code with PyAV, because its own decoder fails with PyAV 19 (BUG-025).

## Why kept apart rather than one "understood text"

The live check (development log, Phase 39) is the argument. On a generated delivery note, OCR read a
crate's stencilled number as **4881**; the vision model said **4821**; neither is guaranteed. The
vision model also called the cracked crate "a square". Merging the two into one text would hide which
engine said what; keeping them apart, labelled, lets every layer weigh them, and lets a person see it.

## Consequences

- An image is evidence only through what was read in it; what was seen informs, and needs
  confirming. This is stricter than a pipeline that trusts a captioner, by design.
- Understanding is slow: a vision call is seconds per image (15.5 s for the delivery note, OCR
  included), a video is bounded to 8 frames, speech runs at many times real time (2.4 s for a 7 s
  clip). The cache makes it a one-time cost per file.
- The libraries are an optional extra (`backend[media]`); without them a file is accepted and says
  what to install. Unit tests never reach a real model: media understanding is off by default in
  tests, and `test_media.py` turns it on with the echo provider.
- Not built: speaker identification, object tracking across frames, audio events other than speech.
