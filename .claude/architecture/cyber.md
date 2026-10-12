# Cyber investigation: logs, indicators, entities, timelines (Phase 52)

Decisions D13 (formats) and D19 (recall). Everything here is read without a model, and every item
cites the line it came from.

## Event logs as citable lines (`app/cyber/eventlog.py`, `tools/formats.py`)

- **Formats**: JSON Lines / NDJSON and Windows or Sysmon XML exports (new kind `event_log`); a `.json`
  array of events; syslog, CSV and plain logs as they are (already one event per line). Native
  `.evtx` is not read yet - export it as XML or JSON.
- **One event per line**: `2026-03-03T09:14:05Z host=WS-12 user=jdoe event=4688 image=... cmd=...`,
  field names mapped from Windows Security, Sysmon and generic JSON onto one short vocabulary; unmapped
  fields kept as `key=value`.
- **XML safety**: a document with a DTD or entity declaration is refused before parsing.

## Indicators (`app/cyber/iocs.py`)

IPv4, domain, URL, e-mail, MD5/SHA-1/SHA-256, CVE, Windows path, registry key. Defanged forms
(`hxxp`, `[.]`, `[@]`) are refanged. A domain needs a known top-level domain or a two-letter country
code (so `Net.WebClient` in a script is not a host); a dotted file name is a file; a path's directories
may contain spaces, its last segment may not, nor a comma (`x.dll,Start`).

## Analysis (`app/cyber/analysis.py`, `GET /api/v1/missions/{id}/cyber`)

- **Entities**: hosts, accounts, processes, addresses, domains, services, decoded scripts.
- **Observed relations**, each with the events that state it: `ACTIVE_ON`, `LOGGED_ON_REMOTELY` (logon
  types 3 and 10), `RAN_ON`, `SPAWNED`, `CONNECTED_TO` (with ports), `INSTALLED_ON` (7045/4697),
  `RAN_ENCODED_COMMAND`. Inferred edges are Phase 53's, kept apart.
- **Encoded PowerShell** (`-enc`, `-EncodedCommand` and abbreviations) decoded from UTF-16LE Base64;
  indicators inside it are reported "via decoded from -EncodedCommand".
- **Per-host and per-account timelines**, in time order, each item a locator.

## Into missions

- The knowledge tool (which `extract_entities` and `extract_claims` tasks use) appends the decoded
  commands and observed relations, each on its line - only when the documents hold events, so no other
  run changes (`tools/knowledge.py` `with_cyber`).
- Evidence text for a line carrying an encoded command has its decoding beside it, labelled
  (`with_decoded`), so a verifier can check a claim about what the command did.
- BUG-037: the date in an ISO timestamp (`2026-03-03T09:14:05Z`) was never read as a date, so every
  claim about when an event happened failed the date check; fixed in `intelligence/temporal.py`.

## Recall of similar cases (`app/cyber/recall.py`, D19)

Opt-in per case (`Case.recall_similar`, `PATCH /api/v1/cases/{id}`). Compares *distinctive* indicators
- domains, URLs, hashes, e-mails, CVEs and non-private addresses - with other CYBER cases' stored
evidence. Shown beside the analysis as context. It never enters a mission: a test checks that nothing
but the cyber endpoint imports the recall.

## Case mode

`CYBER` (set at creation or by PATCH). The console's security-logs panel appears on any run whose
documents hold events; the recall button appears for a run in a case.

## Measured (one live run each, 2026-10-12)

| Scenario | Before the mission integration | After |
|---|---|---|
| cyber_encoded_powershell | 3 findings, none naming the address; claims 0.0 | 4 findings, all verified (0.88), the decoded command and 203.0.113.50 among them |
| cyber_lateral_movement | 2 findings, unverified, SRV-DB missed | 2 findings naming SRV-DB and SRV-FILE (before BUG-037's fix: unverified on dates) |
| cyber_admin_benign (negative) | no findings | no findings |

## ATT&CK mapping and the attack path (Phase 53, ADR-018)

- **Catalogue**: `.agent/attack/enterprise-attack.json`, reduced from the official ATT&CK v15.1 STIX
  bundle (https://github.com/mitre/cti, tag ATT&CK-v15.1; SHA-256 recorded in the file) by
  `backend/scripts/vendor_attack.py`: 637 live techniques, 14 tactics, offline.
- **Rules**: `.agent/config/attack_rules.yaml` - a technique and the event fields that indicate it
  (image, parent, cmd, decoded, event, logon_type, service, dst_port ...). A rule naming a technique
  the catalogue lacks fails loudly. Each mapping lists its rule, what matched and the lines; `source:
  rule`; `needs_validation: true`; a finding citing a mapped line needs review (Phase 50).
- **Attack path**: OBSERVED edges are Phase 52's relations; INFERRED edges come from two rules -
  a decoded command's URL whose file name is then created on the host (DELIVERED), and an account's
  successive remote logons (MOVED_TO, with the caveat that the source address is not known to be the
  first host). Each inferred edge has its reason; none is ever among the observed (tested).
- **3D**: `GET /api/v1/missions/{id}/attack-graph` in the explorer's format; `#/mission/{id}/attack`
  draws observed steps blue (RELATES), inferred amber (INFERRED), techniques purple (MAPS_TO).
- **Benchmark** (`python -m app.cli eval-attack`, CI `scripts/check_attack_report.py`):
  technique_precision 1.000, technique_recall 0.824, held_out_recall 0.400 - the held-out fixture,
  written after the rules, shows an RDP logon, a certutil download and a scheduled task no rule covers.
- **Not built**: model-suggested techniques (they would be labelled `model`).
- **Fixed on the way**: a command line with double quotes (`net group "Domain Admins"`) was cut at
  its first quote when normalised; inner quotes now become single quotes.
