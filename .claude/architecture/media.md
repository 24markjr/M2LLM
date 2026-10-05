# Seeing and hearing: how images, scans, video and audio become evidence (Phase 39)

Why it is built this way: [ADR-012](../decisions/ADR-012-seeing-and-hearing.md). This page is the
mechanism. Code: `backend/app/tools/media.py`, `backend/app/tools/formats.py`.

## The flow

```
upload / mission / analysis / CLI / evaluation
        │
        ▼
formats.prepare(paths)           for each image, video, audio file or PDF not yet understood:
        │                            media.understand(path, sha256)  ─── once per file
        │                               read  (OCR)         images, PDF pages with no text, frames
        │                               seen  (vision model) images, frames          -> "[seen] ..."
        │                               heard (Whisper)      video, audio            -> "[hh:mm:ss] ..."
        │                            cached: .agent/media-cache/<sha256>.json
        ▼
formats.parse(path)              synchronous, no model call: reads the cache into numbered lines
        │
        ▼
the same evidence path as any document: citations `file:rN`, verification, the knowledge layer
```

## What a file becomes

| File | Lines |
|---|---|
| Image | a header (format, size), a line saying what was found, the OCR lines, then `[seen]` lines (summary, up to 8 observations, what was unclear) |
| Scanned PDF | the normal page markers; a page with no text layer gets "(read by OCR ...)" and its OCR lines |
| Video | a timeline ordered by time: `[hh:mm:ss] spoken text`, `[hh:mm:ss] (on screen) text`, `[hh:mm:ss] [seen] ...`. A same-named `.srt`/`.vtt` replaces recognised speech; on-screen and seen lines are kept beside it |
| Audio | `[hh:mm:ss] spoken text`, one segment per line |

## The rules `[seen]` triggers

| Where | Rule |
|---|---|
| `intelligence/knowledge/extraction.py:ground` | A value found only on a `[seen]` line is `grounded=False`: shown, never used for a conflict |
| `integrations/verification.py:described_only` | After any verifier: a `SUPPORTED` finding whose resolved evidence is entirely `[seen]` lines becomes `PARTIALLY_SUPPORTED`, issue `DESCRIBED_ONLY` |

## Bounds (invariant 7) and settings

`MEDIA_UNDERSTANDING` (on), `VISION_MODEL` (`qwen2.5vl:3b`), `WHISPER_MODEL` (`base`),
`MAX_VIDEO_FRAMES` (8), `VIDEO_FRAME_EVERY_S` (15), `MAX_MEDIA_SECONDS` (1800); OCR at most 50 PDF
pages; images sent to the vision model at most 1280 px on the long side.

## Failure, degraded

| Failure | Result |
|---|---|
| `backend[media]` not installed | the file is accepted; its note says `pip install -e "backend[media]"` |
| The vision model fails or is missing | nothing is seen; what was read and heard is kept (BUG-026) |
| Any content error | recorded as "could not be understood: ..."; never fails the upload or the mission |
| `MEDIA_UNDERSTANDING=false` | files are described by size, as in Phase 38, and say understanding is off |
