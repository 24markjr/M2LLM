/**
 * The composer (Phase U4): the question, the files, and how to run it.
 *
 * Files are uploaded the moment they are attached (so a scan is read, a recording heard, and the
 * upload is evidence with its hash) and shown as chips. Enter sends; Shift+Enter is a new line.
 * Sending opens a new case named after the question unless another case (or none) is chosen, sets
 * the chosen sensitivity on the files uploaded here, starts the investigation and opens it.
 */

import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { api, ApiError } from "../api/client";
import type { CaseList, FormatSpec, StoredDocument } from "../api/types";
import { acceptAttribute, contextFileName, isSupported } from "../components/documents";
import { casesChanged } from "../shell/Sidebar";
import { Button, Dialog, Notice, TextArea, TextInput, useToast } from "../ui/components";
import { IconClose, IconPlus } from "../ui/icons";
import { caseTitleFor, MODE_PLANS, MODES, questionProblem, type Mode } from "./modes";
import type { Pack, Sensitivity } from "./packs";

export interface Attached {
  name: string;
  kind: string;
  /** Set for files uploaded in this composer: their sensitivity is set on sending. */
  evidenceId?: string | undefined;
  detail: string;
  injection: boolean;
  readable: boolean;
}

export interface ComposerDraft {
  question: string;
  files: string[];
  mode: Mode;
  /** Bumped by the home page so the same starter can be applied twice. */
  key: number;
}

const SENSITIVITIES: { value: Sensitivity; label: string }[] = [
  { value: "UNCLASSIFIED", label: "Unclassified" },
  { value: "INTERNAL", label: "Internal" },
  { value: "CONFIDENTIAL", label: "Confidential" },
  { value: "RESTRICTED", label: "Restricted" },
];

export function Composer({ pack, draft }: { pack: Pack; draft: ComposerDraft | null }) {
  const notify = useToast();
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>(pack.mode);
  const [sensitivity, setSensitivity] = useState<Sensitivity>(pack.sensitivity);
  const [caseChoice, setCaseChoice] = useState("new");
  const [cases, setCases] = useState<CaseList["cases"]>([]);
  const [files, setFiles] = useState<Attached[]>([]);
  const [formats, setFormats] = useState<FormatSpec[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.getFormats().then(setFormats).catch(() => setFormats([]));
    api.listCases().then((b) => setCases(b.cases)).catch(() => setCases([]));
  }, []);

  // A new pack sets its defaults.
  useEffect(() => {
    setMode(pack.mode);
    setSensitivity(pack.sensitivity);
  }, [pack]);

  // A starter fills the composer.
  useEffect(() => {
    if (!draft) return;
    setQuestion(draft.question);
    setMode(draft.mode);
    setFiles(draft.files.map((name) => ({ name, kind: kindOf(name), detail: "example", injection: false, readable: true })));
    setError("");
    textarea.current?.focus();
  }, [draft]);

  // The box grows with the question, up to a limit.
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 280)}px`;
  }, [question]);

  const accept = useMemo(() => acceptAttribute(formats), [formats]);
  const modeInfo = MODES.find((m) => m.id === mode) ?? MODES[0];
  const problem = questionProblem(question);
  const readable = files.filter((f) => f.readable);

  const upload = async (picked: File[]) => {
    const unsupported = formats.length ? picked.filter((f) => !isSupported(f.name, formats)) : [];
    const accepted = picked.filter((f) => !unsupported.includes(f));
    setError(unsupported.length ? `Not a type the engine reads: ${unsupported.map((f) => f.name).join(", ")}` : "");
    if (!accepted.length) return;
    setUploading(true);
    try {
      const results = await api.uploadDocuments(accepted);
      setFiles((current) => [
        ...current.filter((f) => !results.some((r) => r.name === f.name)),
        ...results.map((r) => ({
          name: r.name,
          kind: r.kind,
          evidenceId: r.evidence_id,
          detail: r.has_text ? r.understood || sizeLabel(r.bytes) : r.note || "no text yet",
          injection: Object.keys(r.injection.hits).length > 0,
          readable: r.has_text,
        })),
      ]);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const send = async () => {
    if (problem || sending) return;
    setSending(true);
    setError("");
    try {
      // Sensitivity on the files uploaded here (Library files keep theirs).
      if (sensitivity !== "UNCLASSIFIED") {
        await Promise.all(
          files.filter((f) => f.evidenceId).map((f) => api.updateEvidence(f.evidenceId as string, { classification: sensitivity })),
        );
      }
      let caseId: string | undefined;
      if (caseChoice === "new") {
        const created = await api.openCase({
          title: caseTitleFor(question),
          description: question.trim(),
          mode: mode === "security" ? "CYBER" : "GENERAL",
        });
        caseId = created.case_id;
      } else if (caseChoice !== "none") {
        caseId = caseChoice;
      }
      const mission = await api.createMission(question.trim(), readable.map((f) => f.name), undefined, caseId, mode);
      casesChanged();
      notify("Investigation started.", "success");
      window.location.hash = `#/mission/${mission.run_id}`;
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "The investigation could not be started.");
      setSending(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files.length) void upload(Array.from(e.dataTransfer.files));
  };

  return (
    <div className="composer-wrap">
      <div
        className={`composer ${drag ? "drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        {files.length ? (
          <ul className="composer-files" aria-label="Attached files">
            {files.map((f) => (
              <li key={f.name} className={`file-chip ${f.readable ? "" : "waiting"}`} title={f.detail}>
                <span className="file-chip-kind">{f.kind}</span>
                <span className="file-chip-name">{f.name}</span>
                {f.injection ? <span className="file-chip-flag" title="Text resembling a prompt injection: read as data, flagged">flagged</span> : null}
                {!f.readable ? <span className="file-chip-flag">no text yet</span> : null}
                <button type="button" className="icon-button" aria-label={`Remove ${f.name}`} onClick={() => setFiles((c) => c.filter((x) => x.name !== f.name))}>
                  <IconClose size={14} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <textarea
          ref={textarea}
          className="composer-input"
          rows={2}
          value={question}
          placeholder={modeInfo?.placeholder}
          aria-label="Your question"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKey}
        />

        <div className="composer-bar">
          <div className="composer-attach">
            <button
              type="button"
              className="icon-button composer-plus"
              aria-label="Add files"
              aria-haspopup="menu"
              aria-expanded={menu}
              onClick={() => setMenu((m) => !m)}
              disabled={uploading}
            >
              {uploading ? <span className="ui-spinner" aria-hidden="true" /> : <IconPlus />}
            </button>
            {menu ? (
              <div className="menu composer-menu" role="menu" onMouseLeave={() => setMenu(false)}>
                <button type="button" role="menuitem" onClick={() => { setMenu(false); fileInput.current?.click(); }}>
                  Upload files
                </button>
                <button type="button" role="menuitem" onClick={() => { setMenu(false); setLibraryOpen(true); }}>
                  From the Library
                </button>
                <button type="button" role="menuitem" onClick={() => { setMenu(false); setPasteOpen(true); }}>
                  Paste text
                </button>
              </div>
            ) : null}
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              accept={accept}
              onChange={(e) => {
                if (e.target.files?.length) void upload(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
          </div>

          <div className="composer-modes" role="radiogroup" aria-label="Mode">
            {MODES.map((m) => (
              <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} className={mode === m.id ? "on" : ""} title={m.hint} onClick={() => setMode(m.id)}>
                {m.label}
              </button>
            ))}
          </div>

          <span className="composer-spacer" />

          <label className="composer-select" title="Which case this investigation is filed in">
            <span className="ui-sr">Case</span>
            <select value={caseChoice} onChange={(e) => setCaseChoice(e.target.value)}>
              <option value="new">New case</option>
              {cases.map(({ case: c }) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id}: {c.title.slice(0, 40)}
                </option>
              ))}
              <option value="none">No case</option>
            </select>
          </label>
          <label className="composer-select" title="Set on the files you upload here. Confidential and above are never sent to a cloud model.">
            <span className="ui-sr">Sensitivity</span>
            <select value={sensitivity} onChange={(e) => setSensitivity(e.target.value as Sensitivity)}>
              {SENSITIVITIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <Button variant="primary" busy={sending} disabled={!!problem || uploading} onClick={() => void send()} aria-label="Start the investigation">
            Start
          </Button>
        </div>
      </div>

      <div className="composer-foot">
        <span>{modeInfo?.hint}.</span>
        {MODE_PLANS[mode] ? <span className="composer-plan">{MODE_PLANS[mode]}</span> : null}
        {question && problem ? <span className="composer-problem">{problem}</span> : null}
        {!files.length ? <span>No files attached: the engine will only have your question to go on.</span> : null}
      </div>
      {pack.notice ? <Notice tone="warning">{pack.notice}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}

      <LibraryPicker
        open={libraryOpen}
        examples={[...new Set(pack.starters.flatMap((s) => s.files))]}
        chosen={files.map((f) => f.name)}
        onClose={() => setLibraryOpen(false)}
        onChoose={(names) => {
          setFiles((current) => [
            ...current,
            ...names
              .filter((n) => !current.some((f) => f.name === n))
              .map((name) => ({ name, kind: kindOf(name), detail: "from the Library", injection: false, readable: true })),
          ]);
          setLibraryOpen(false);
        }}
      />
      <PasteText
        open={pasteOpen}
        taken={files.map((f) => f.name)}
        onClose={() => setPasteOpen(false)}
        onAdd={(file) => {
          setPasteOpen(false);
          void upload([file]);
        }}
      />
    </div>
  );
}

function LibraryPicker({
  open,
  examples,
  chosen,
  onClose,
  onChoose,
}: {
  open: boolean;
  examples: string[];
  chosen: string[];
  onClose: () => void;
  onChoose: (names: string[]) => void;
}) {
  const [stored, setStored] = useState<StoredDocument[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!open) return;
    setPicked([]);
    setFilter("");
    api.listUploads().then(setStored).catch(() => setStored([]));
  }, [open]);

  const names = [...new Set([...examples, ...stored.map((s) => s.name)])].filter(
    (n) => !chosen.includes(n) && n.toLowerCase().includes(filter.toLowerCase()),
  );
  const toggle = (n: string) => setPicked((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n]));

  return (
    <Dialog
      open={open}
      title="Add from the Library"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!picked.length} onClick={() => onChoose(picked)}>
            Add {picked.length || ""}
          </Button>
        </>
      }
    >
      <TextInput label="Find a file" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Name contains..." />
      <ul className="picker-list">
        {names.map((n) => (
          <li key={n}>
            <label>
              <input type="checkbox" checked={picked.includes(n)} onChange={() => toggle(n)} />
              <span className="mono">{n}</span>
              {examples.includes(n) ? <span className="ui-badge accent">example</span> : null}
            </label>
          </li>
        ))}
        {names.length === 0 ? <li className="dim">Nothing to add.</li> : null}
      </ul>
    </Dialog>
  );
}

function PasteText({
  open,
  taken,
  onClose,
  onAdd,
}: {
  open: boolean;
  taken: string[];
  onClose: () => void;
  onAdd: (file: File) => void;
}) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  useEffect(() => {
    if (open) {
      setName("");
      setText("");
    }
  }, [open]);
  return (
    <Dialog
      open={open}
      title="Paste text"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!text.trim()}
            onClick={() => onAdd(new File([text.trim()], contextFileName(name, taken), { type: "text/plain" }))}
          >
            Add as a file
          </Button>
        </>
      }
    >
      <TextInput label="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. witness_call_notes" />
      <TextArea label="Text" rows={8} value={text} onChange={(e) => setText(e.target.value)} hint="Kept as a text file in the Library, with its hash, like any upload." />
    </Dialog>
  );
}

function kindOf(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return ext || "file";
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
