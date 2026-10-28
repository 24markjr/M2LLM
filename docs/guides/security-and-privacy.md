# JARVIS - Security and privacy

What JARVIS protects, how, and what it does not claim. Written for a customer's security and privacy
reviewers. Each statement below is something the product does today, with where it is checked.

## 1. Where data lives

- **Cloud installation**: Google Cloud, region asia-south1 (Mumbai). The application, databases,
  files and backups stay in that project; disks and the backup bucket are encrypted at rest with
  Google-managed keys. Customer-managed keys are not set up.
- **The model** runs on hardware we operate (an open-weights model through Ollama), reached over a
  private Tailscale network. Customer documents are not sent to a third-party AI service.
- **On-premise**: the same product inside the customer's network, with no outside connection
  required (see [on-premise](on-premise.md)).
- **Indian languages** are translated by IndicTrans2 (AI4Bharat, MIT licence) running on the
  application server's CPU, pinned by revision; the receipt of every investigation names the engine
  and version that translated each document. **Bhashini** (MeitY) is used only when an organisation
  turns it on, and only for Unclassified (optionally Internal) material: Confidential, Restricted
  and unclassified-by-default material never leaves our cloud (`app/language/routing.py`, tested in
  `tests/unit/test_language.py`). Read aloud uses the browser's own voice unless Bhashini is allowed;
  a spoken question is transcribed on our server and the recording is not kept.

## 2. Access

- Every API route requires a signed-in user; a test calls every route anonymously and expects `401`,
  and `backend/scripts/security_check.py` repeats it against the live site at each deploy.
- Passwords are stored as scrypt hashes; sessions as SHA-256 of a random token, in an HttpOnly,
  Secure, SameSite cookie. Five failed sign-ins lock an address for 15 minutes.
- Roles (viewer, reviewer, analyst, admin) are checked on every request, from one table.
- **Organisations are isolated**: every store filters by the signed-in user's organisation, and one
  check in front of every route refuses another organisation's run, case or evidence item as "not
  found". Tested with two organisations through the API.
- The API reads files only by name, from the organisation's own uploads - never a path on the server.
- Per-account request limits; the queue refuses new work when full.

## 3. The network edge

HTTPS only (HTTP redirects), HSTS, a Content-Security-Policy on the console, frame denial, no
`Server` banner. Only ports 80 and 443 are open; administration is through Google's Identity-Aware
Proxy. Secrets are in Secret Manager, written to the server at deploy time, readable by root only.

## 4. Evidence integrity

Every file is fingerprinted (SHA-256) on arrival and kept unchanged; every read, citation and report
is appended to its chain of custody, which the database refuses to update or delete. Before an
investigation reads a file, its fingerprint is checked; a changed file is excluded and the
investigation says so. Reports carry their own content hash and the run's receipt hash.

This records what happened to a file **inside JARVIS**. It is not a forensic examination of the
file's origin, and JARVIS makes no claim of forensic-grade or court-admissible evidence handling.

## 5. Privacy (DPDP Act 2023)

- **Retention** per organisation, applied daily (evidence and custody are kept).
- **Masking** of e-mail, phone, Aadhaar, PAN and card numbers in exported reports.
- **Data-subject requests**: find every place a person appears; erase investigations and messages
  that hold it; evidence files are listed for a legal-hold decision.
- **Audit log** of every change and sign-in, exportable as CSV.
- What JARVIS processes is what the customer uploads. Indian-language processing through Bhashini,
  when added, will be routed only for data the customer classifies as allowed to leave the project.

## 6. Answers

- Every claim shown cites lines of the documents and is verified before it is marked: a model
  verifier, a lexical checker and an entailment model; arithmetic is redone by code.
- Text inside documents is treated as data, never as instructions: documents are scanned for prompt
  injection and quoted to the model inside marked blocks.
- The model's internal reasoning is not stored or shown.
- A verified claim can still be wrong. Confidence is an evidence score, not a calibrated probability,
  and is labelled as such.

## 7. Assurance done, and not done

Done: automated tests for every control above (1,400+ backend tests), a dependency audit at each
release (`pip-audit`, `npm audit` - findings fixed), and the scripted outside-in check on the live
site. **Not done: an independent penetration test.** It should precede any regulated deployment.
