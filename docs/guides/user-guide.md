# JARVIS - User guide

JARVIS investigates documents. You give it files and a question; it reads them, finds what bears on
the question, and reports each finding with the exact lines it rests on - checked before you see it.
It never asks you to trust a sentence it cannot point to.

This guide is for investigators and reviewers. Administrators: see the [admin guide](admin-guide.md).

## 1. Signing in

Open the address your administrator gave you and sign in with your e-mail and password. Change the
first password at once: **Settings > Your account**. A session lasts 12 hours. Five wrong passwords
lock an address for 15 minutes.

What you can do depends on your role:

| Role | Can |
|---|---|
| Viewer | Read everything in your organisation; change nothing |
| Reviewer | A viewer who also reviews and challenges findings |
| Analyst | Run investigations, add evidence, manage cases |
| Admin | Everything, including people, retention and data-subject requests |

You only ever see your own organisation's cases, files and investigations.

## 2. A case

A **case** is the matter you are working on: its files (the evidence), its investigations, and the
conversation about it. Start at **Cases > New case**, give it a title, then **Add files to this case**.

Files are evidence from the moment they arrive: each is fingerprinted (SHA-256), stored unchanged,
and every use of it - read, cited, reported - is written to its **chain of custody** (the Evidence
Locker). Supported: PDF (text and scanned), Word, Excel and CSV, text and logs, images, audio and
video. Scans, photos, audio and video are read by OCR and speech recognition first.

## 3. Investigating

**New investigation** in a case: choose its files and write the question as you would to a
colleague - "Did Orion's spend exceed what was approved, and who approved it?". JARVIS plans the
work, reads, reasons, verifies each finding and writes the answer. You can watch it work, and
**Stop** it.

If several investigations are running, yours waits its turn; the page shows its place in the queue.
If the question is too vague to plan, JARVIS asks what you mean - answer in the box and it starts
again with your answer.

### Reading the answer

- Every sentence carries a mark: **verified**, **partially supported**, **unsupported** or
  **unverified**. Only verified findings are counted as established.
- Every finding lists its **citations** - file and line, or page. Click one to see the line in its
  document, highlighted.
- **Strong / moderate / weak evidence** says how much and how good the evidence is - how many
  documents, how direct, how authoritative, whether the checks agreed. It is not a probability:
  "Why?" on a finding shows how the score was computed.
- A finding's **history** shows how it was created, verified, reviewed, challenged and re-checked.
- **Challenge** looks for lines in the documents that would make the finding wrong. Every verified
  finding is challenged automatically when the investigation ends.

**Run again** repeats the investigation on the same files; **Edit the question** runs a changed
question. The case page compares two investigations finding by finding.

## 4. Asking about a case

**Ask about this case** on the case page is a conversation. Ask follow-up questions in plain words;
JARVIS remembers the conversation. It searches the case's files, reads passages, does arithmetic,
and answers claim by claim:

- You see what it is doing as it does it ("Searching the case for 'approved budget'"), then the
  answer's words, then each claim's mark as soon as it is checked. A claim marked "checking" is
  still being checked.
- Every claim cites lines of the case's files; click a citation to open it.
- **Recheck F-002** re-verifies a finding against the case's files as they are now and shows before
  and after. When files were added to the case after an investigation, the case page tells you which
  findings to re-check.
- **Ask again** regenerates an answer; **edit** changes your question. Earlier versions are kept -
  **show earlier versions**.

## 5. Reports

On an investigation, **Build the report**, then **Open the report** (a page you can print) or
download **PDF** or **DOCX** - the same document. It holds an executive brief, the findings table,
contradictions with both sources quoted, a timeline, gaps and next evidence, and an appendix with
every file's fingerprint and the run's receipt. Every export is a numbered version signed with the
report's and the run's hashes, listed under the report.

## 6. Indian languages

**Files in an Indian language** - Hindi, Marathi, Nepali, Bengali, Assamese, Punjabi, Gujarati,
Odia, Tamil, Telugu, Kannada, Malayalam or Urdu - are read through an English translation made line
by line, so line 7 of the translation is line 7 of the original. The original stays the evidence:
click a citation in the case's conversation and the original and the translation open side by side, with the cited line
highlighted in both.

- A finding that rests **only** on translated lines is never marked verified on its own: it goes to
  review, for someone who reads the language to check the translation against the original. A
  finding that also cites an original line - a Hindi report against an English ledger - is verified
  as usual.
- Every figure on a translated line is checked against the original. If one did not survive, the
  original's figures are written on the line and the viewer warns you.
- Scanned pages in Indian scripts are **not** read yet (OCR reads Latin script only). Type or export
  such documents as text.

**Asking in your language**: choose it under **Language** in *Ask about this case*. Type in its own
script, in Roman letters ("kitna bhugtan hua?"), or press **Speak**. The question is read in
English - you see the English it was read as - and the answer comes in English, the verified
master, with its translation into your language below it, labelled as a machine translation.
**Read aloud** speaks it with your browser's own voice. With Hindi chosen, the panel itself is in
Hindi. A question typed on the home page in Hindi runs in English too; the investigation page
shows it as asked.

**Reports in your language**: under the report, pick a language for **Open in ...** or **DOCX
in ...**: the same report, translated, with a banner naming the engine. Quotes from the evidence,
finding IDs, file names and hashes are kept exactly as written. The PDF is English only: it cannot
yet draw Indian scripts correctly.

## 7. What JARVIS does not do

- It does not decide anything for you. A finding is a claim with evidence; a reviewer decides.
- It does not prove that a file is authentic. The chain of custody records what happened to a file
  *in JARVIS*; it is not a forensic examination of where the file came from.
- It can be wrong. A wrong claim it verifies is possible - that is why every claim shows its lines,
  and why findings that matter need a reviewer's decision.
