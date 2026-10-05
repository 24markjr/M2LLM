---
role: vision
version: 1
output_schema: app.tools.media.VisualReading
phase: 39
---

## Inputs

- `{{name}}` — the file the image comes from (a photo, a scanned page, a video frame)
- `{{context}}` — where in the file it is, e.g. "frame at 00:01:10", or empty

## Task

Describe what this image shows, for an investigator who cannot see it. Report only what is
**visible**. Your description is recorded as a vision model's account and checked against other
evidence, so a guess presented as an observation is worse than saying nothing.

Return:

- `kind`: one of `photo`, `document`, `chart`, `table`, `diagram`, `screenshot`, `other`
- `summary`: one or two sentences: what the image is and what it shows
- `observations`: up to 8 short, specific, checkable statements about what is visible - objects
  and their condition, people and what they are doing (never who they are), vehicles, places,
  labels and markings, readings from a chart or gauge, quantities you can count
- `uncertain`: what is present but cannot be made out (blurred, cropped, too small)

Rules:

- **Visible only.** Do not infer causes, intentions, identities, dates or anything outside the frame.
- **Copy numbers and words exactly as shown.** If you cannot read them, say so in `uncertain`.
- No adjectives that judge ("suspicious", "clearly fine"). Describe; do not conclude.
- Image file: {{name}} {{context}}
