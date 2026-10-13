# Home and the composer (Phase U4)

Code: `frontend/src/home/` - `HomePage.tsx`, `Composer.tsx`, `packs.ts`, `modes.ts`,
`attention.ts`, `home.css`. `#/` is the home page; the case list moved to `#/cases`.

## The home page

"What do you need to find out?", a one-line account of what JARVIS does, the domain packs, the
composer, two starter questions for the chosen pack, "Needs your attention", and links to the quick
analysis (no investigation), the detailed form (`#/new`) and all cases.

## The composer

- **The question**, a box that grows with it. Enter starts; Shift+Enter is a new line. The reason a
  question would be refused (under 8 characters, over 2,000 with the mode's framing) is shown, and
  Start stays disabled until it is fixed.
- **Files**, attached by the + menu (Upload files, From the Library, Paste text) or by dropping them
  on the box. An upload happens at once - so a scan is read and a recording heard, and the file is
  evidence with its hash - and appears as a chip with its kind; a file with no text yet is dashed, a
  file whose text resembles a prompt injection is flagged. From the Library lists earlier uploads
  and the pack's example files. Pasted text becomes a `.txt` upload.
- **Mode**: Investigate, Compare, Timeline, Security logs.
- **Case**: a new case named after the first sentence of the question (the default, so every
  investigation appears in the sidebar), an existing case, or none.
- **Sensitivity**: set on the files uploaded in this composer when it starts (`PATCH /evidence/{id}`
  classification). Files chosen from the Library keep theirs.

Starting: classify the new uploads, open the case if asked (mode CYBER for Security logs), start the
investigation (`POST /missions` with the case), tell the sidebar, open the investigation.

## Modes are wording, not engines

Every mode runs the same investigation: plan, read, verify, cite. A mode puts a framing sentence in
front of the question (`objectiveFor`) so the intent engine plans the operations it names:

| Mode | Sent to the engine |
|---|---|
| Investigate | the question as asked |
| Compare | "Compare the attached documents: where do they agree, and where do they contradict each other?" + the question |
| Timeline | "Build a timeline of the events in the attached documents, and note any dates that conflict." + the question |
| Security logs | "Examine the attached security logs for malicious activity." + the question; a new case is CYBER |

Saying so here, and in the composer's hint line, matters: a mode that looked like a different engine
would be a claim the system does not make.

## Domain packs

General, Investigation, Finance and audit, Legal, Healthcare, Cyber (`packs.ts`). A pack sets the
starter questions, the default mode and the default sensitivity of uploads (Confidential for all but
General). Healthcare shows: "Record review and decision support only - not a diagnosis. Every
statement is cited to the records; a clinician decides." Starters with files attach real example
files from `.agent/fixtures/documents` (Aurora, shipment 4821, Lyra, Orion, Vega, the cyber logs),
so each runs as shown; Legal and Healthcare have no example files in the repository and their
starters attach none. The chosen pack is remembered per browser (`jarvis.pack`). Per-pack entity
types, report templates and severity rules are Phase B7.

## Needs your attention

From `GET /missions` (`attentionItems`): running investigations; finished ones from the last seven
days with findings that did not all verify; finished ones with questions the evidence left open. At
most six, running first. Review decisions are not yet counted (that needs each run's reviews; U5).

## Verified

Unit tests for modes, case titles, question checks, packs and the attention list. Home checked once
in headless Chrome at 1440 px and 600 px against a temporary API; starting an investigation was not
part of the check, since it would have written a case and a run into the user's database.
