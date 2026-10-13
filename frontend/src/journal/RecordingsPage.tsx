/**
 * Recordings (Phase U5): finished investigations as records - what was asked, how it ended, what it
 * found, its case - with delete, and replay in the journal itself.
 *
 * Replaced the row of 101 unnamed buttons. Failed runs that found nothing and second copies of a run
 * are hidden by default (U1) and can be shown or deleted together.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { RecordingSummary } from "../api/types";
import { SPEEDS, useReplay, type Speed } from "../hooks/useReplay";
import { Badge, Button, Card, ConfirmDialog, DataTable, Notice, useToast, type Column } from "../ui/components";
import { IconTrash } from "../ui/icons";
import { Journal } from "./JournalPage";

export function RecordingsPage() {
  const notify = useToast();
  const [rows, setRows] = useState<RecordingSummary[]>([]);
  const [showHidden, setShowHidden] = useState(false);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState<null | { kind: "one"; row: RecordingSummary } | { kind: "hidden" | "all" }>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .listRecordings(showHidden)
      .then((r) => {
        setRows(r);
        setError("");
      })
      .catch((exc: unknown) => setError(exc instanceof ApiError ? exc.message : "Recordings could not be loaded."));
  }, [showHidden]);
  useEffect(load, [load]);

  const doDelete = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === "one") {
        await api.deleteRecording(confirm.row.file);
        notify("Recording deleted. The investigation itself is kept.", "success");
      } else {
        const result = await api.deleteRecordings(confirm.kind);
        notify(`${result.deleted} recording(s) deleted${result.kept ? `, ${result.kept} kept (in the repository)` : ""}.`, "success");
      }
      setConfirm(null);
      load();
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "It could not be deleted.", "error");
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<RecordingSummary>[] = [
    {
      key: "q",
      header: "Question",
      render: (r) => (
        <a href={`#/replay/${encodeURIComponent(r.file)}`} className="recording-q">
          {r.objective || r.run_id}
        </a>
      ),
    },
    { key: "o", header: "Ended", nowrap: true, render: (r) => <Outcome row={r} /> },
    { key: "f", header: "Findings", align: "right", nowrap: true, render: (r) => (r.findings === undefined ? "-" : `${r.verified ?? 0} / ${r.findings}`) },
    { key: "c", header: "Case", nowrap: true, render: (r) => (r.case_id ? <a href={`#/case/${r.case_id}`}>{r.case_id}</a> : "-") },
    { key: "d", header: "Took", align: "right", nowrap: true, render: (r) => duration(r.duration_ms) },
    { key: "w", header: "Recorded", nowrap: true, render: (r) => (r.recorded_at ? new Date(r.recorded_at).toLocaleString() : "-") },
    {
      key: "x",
      header: "",
      nowrap: true,
      label: "Delete",
      render: (r) =>
        r.committed ? (
          <span className="dim" title="Part of the repository: removed with git, not here">kept</span>
        ) : (
          <button type="button" className="icon-button" aria-label={`Delete the recording of ${r.objective}`} onClick={() => setConfirm({ kind: "one", row: r })}>
            <IconTrash size={16} />
          </button>
        ),
    },
  ];

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Card
        title="Recordings"
        meta={`${rows.length} shown · replayed, never re-run`}
        actions={
          <>
            <label className="recording-toggle">
              <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Show failed and duplicate runs
            </label>
            <Button size="sm" onClick={() => setConfirm({ kind: "hidden" })}>
              Delete failed and duplicates
            </Button>
            <Button size="sm" variant="danger" onClick={() => setConfirm({ kind: "all" })}>
              Delete all
            </Button>
          </>
        }
        flush
      >
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.file}
          caption="Recorded investigations"
          empty="No recordings. Every investigation records itself when it ends."
        />
      </Card>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm?.kind === "one" ? "Delete this recording?" : confirm?.kind === "hidden" ? "Delete failed and duplicate recordings?" : "Delete every recording?"
        }
        body={
          <p>
            {confirm?.kind === "one"
              ? "The replay of this run goes. The investigation itself, its findings and the audit log are kept."
              : confirm?.kind === "hidden"
                ? "Recordings of runs that failed without finding anything, and second copies of a run, go."
                : "Every local recording goes. Investigations are kept; recordings committed to the repository are kept."}
          </p>
        }
        confirmLabel="Delete"
        typeToConfirm={confirm?.kind === "all" ? "delete" : undefined}
        busy={busy}
        onClose={() => setConfirm(null)}
        onConfirm={() => void doDelete()}
      />
    </>
  );
}

function Outcome({ row }: { row: RecordingSummary }) {
  const tone = row.outcome === "COMPLETED" ? "verified" : row.outcome === "FAILED" ? "unsupported" : "unknown";
  return (
    <span className="recording-outcome">
      <Badge tone={tone}>{row.outcome.toLowerCase().replaceAll("_", " ") || "unknown"}</Badge>
      {row.hidden ? <span className="dim" title={row.hidden}>hidden</span> : null}
    </span>
  );
}

function duration(ms: number): string {
  if (!ms) return "-";
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** A recording played back in the journal: the same page a live run uses, with playback controls. */
export function ReplayJournal({ file }: { file: string }) {
  const replay = useReplay(file);
  if (replay.loading) return <div className="journal-loading">Loading the recording.</div>;
  const progress = replay.total ? (replay.position / replay.total) * 100 : 0;
  return (
    <>
      <div className="replay-bar" role="region" aria-label="Replay">
        <Badge tone="accent">Replay</Badge>
        <span className="replay-when">
          Recorded {replay.recording ? new Date(replay.recording.recorded_at).toLocaleString() : ""}
          {replay.recording?.model ? ` on ${replay.recording.model}` : ""} - nothing is running now
        </span>
        <div className="replay-controls-u5">
          {replay.playing ? (
            <Button size="sm" onClick={replay.pause}>
              Pause
            </Button>
          ) : (
            <Button size="sm" variant="primary" onClick={replay.position >= replay.total ? replay.restart : replay.play}>
              {replay.position >= replay.total ? "Play again" : "Play"}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={replay.skipToEnd}>
            Skip to the end
          </Button>
          <label className="replay-speed">
            <span className="ui-sr">Speed</span>
            <select value={replay.speed} onChange={(e) => replay.setSpeed(Number(e.target.value) as Speed)}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}x
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="replay-progress" aria-hidden="true">
          <span style={{ width: `${progress}%` }} />
        </div>
      </div>
      <Journal view={replay} />
    </>
  );
}
