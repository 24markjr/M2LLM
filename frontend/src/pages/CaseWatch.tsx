/**
 * A case's watch folder (v4 Phase 10): files dropped in the folder are taken in as evidence every
 * few minutes, and the case's latest investigation can run again with them - or on a schedule.
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { WatchView } from "../api/types";
import { useToast } from "../ui/components";

export function CaseWatch({ caseId }: { caseId: string }) {
  const notify = useToast();
  const [watch, setWatch] = useState<WatchView | null>(null);
  useEffect(() => {
    api
      .caseWatch(caseId)
      .then(setWatch)
      .catch(() => setWatch(null));
  }, [caseId]);
  if (!watch) return null;

  const save = async (next: WatchView) => {
    try {
      setWatch(
        await api.saveCaseWatch(caseId, {
          enabled: next.enabled,
          rerun_on_new_files: next.rerun_on_new_files,
          rerun_every_days: next.rerun_every_days,
        }),
      );
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "Could not save.", "error");
    }
  };
  const scan = async () => {
    try {
      const done = await api.scanCaseWatch(caseId);
      notify(
        done.taken.length
          ? `Took in ${done.taken.join(", ")}${done.rerun ? `; started ${done.rerun}` : ""}.`
          : done.rerun
            ? `Started ${done.rerun} (${done.reason}).`
            : "Nothing new in the folder.",
        "success",
      );
    } catch (exc) {
      notify(exc instanceof ApiError ? exc.message : "Could not look in the folder.", "error");
    }
  };

  return (
    <div className="panel">
      <h2>Watch folder</h2>
      <div className="panel-body">
        <div className="row">
          <label>
            <input type="checkbox" checked={watch.enabled} onChange={(e) => void save({ ...watch, enabled: e.target.checked })} />{" "}
            Take in files dropped into <span className="mono">{watch.folder}</span>
          </label>
        </div>
        {watch.enabled ? (
          <div className="row">
            <label>
              <input
                type="checkbox"
                checked={watch.rerun_on_new_files}
                onChange={(e) => void save({ ...watch, rerun_on_new_files: e.target.checked })}
              />{" "}
              Re-run the latest investigation when files arrive
            </label>
            <label>
              and every{" "}
              <input
                type="number"
                min={0}
                max={365}
                style={{ width: 64 }}
                value={watch.rerun_every_days}
                onChange={(e) => void save({ ...watch, rerun_every_days: Number(e.target.value) })}
              />{" "}
              day(s) (0 = never)
            </label>
            <button onClick={() => void scan()}>Look now</button>
          </div>
        ) : null}
        <p className="dim">
          {Object.keys(watch.seen).length} file(s) taken in so far
          {watch.last_rerun_at ? ` · last re-run ${new Date(watch.last_rerun_at).toLocaleString()}` : ""}. Each arrives
          with its chain of custody, like an upload.
        </p>
      </div>
    </div>
  );
}
