# Bug Log

Defects found during development, what caused them, and how they were fixed.
A bug is recorded here even when the fix is trivial — the pattern matters more than the
individual defect.

---

## BUG-001 — Healthcheck crashed rendering its own report on the Windows console

**Found:** 2026-09-23, Phase 0
**Severity:** Low (tooling only) — but it masked the result it was meant to report
**Status:** Fixed

**Symptom**

`python scripts/healthcheck.py` printed the first two check rows, then died:

```
UnicodeEncodeError: 'charmap' codec can't encode character '→'
```

**Cause**

The report renderer used `→` for hints and `—` in two detail strings. The Windows console
defaults to code page 1252, which has no mapping for either. The failure happened *while
printing a FAIL row*, so the first real failure the script detected was also the first thing
that broke it.

**Fix**

Operator-facing output is ASCII-only. `→` became `->`, em dashes became hyphens. Non-ASCII
remains fine in comments and docstrings, which are never written to the console.

**Lesson recorded**

Anything printed to a terminal on Windows stays in ASCII unless the code page is explicitly
set. This applies to the CLI entry point (Phase 9) and the evaluation report renderer
(Phase 20), both of which will print status output.
