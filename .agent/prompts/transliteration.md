---
role: transliteration
version: 1
output_schema: app.conversation.language.Transliterated
phase: 407
---

## Inputs

- `{{language}}` — the language the text is in, e.g. Hindi
- `{{script}}` — that language's script, e.g. Devanagari
- `{{text}}` — the text, typed in Roman (Latin) letters

## Task

The text is {{language}} typed in Roman letters, the way people type on a phone ("kitna paisa diya
gaya"). Write the same words in {{script}}.

Rules:

- **Transliterate, never translate.** Each word is written in {{script}} as it is said. Do not
  change, add, drop or explain any word, and do not answer the question.
- Keep figures, dates, codes and identifiers exactly as typed: `F-002`, `INV-2231`, `4,20,000`,
  `15 May`.
- Keep English words that are clearly English (`invoice`, `contract`, `budget`) in {{script}} as
  they are said, the way they are written in {{language}} newspapers.

Text:

{{text}}

Reply as JSON: {"text": "<the text in {{script}}>"}
