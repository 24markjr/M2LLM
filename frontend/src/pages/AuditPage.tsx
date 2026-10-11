/**
 * The audit log (Phase 50): every write the API received - accepted or refused - and the system's
 * own actions, newest first. Append-only: nothing on this page can be edited, here or anywhere.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { AuditEntry } from "../api/types";
import { auditLine } from "../components/review";

export function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getAudit(target)
      .then(setEntries)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, [target]);

  return (
    <div className="panel">
      <h2>
        Audit log <span className="count">{entries.length} entries</span>
      </h2>
      <div className="panel-body">
        <input
          aria-label="Filter by target"
          placeholder="filter: a run id, a case id, an evidence id, an action"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
        {error ? <div className="notice error">{error}</div> : null}
        <table className="metrics">
          <thead>
            <tr>
              <th>When</th>
              <th>What</th>
              <th>Target</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.entry_id}>
                <td className="dim">{new Date(e.at).toLocaleString()}</td>
                <td className="mono">{auditLine(e)}</td>
                <td className="mono">{e.target}</td>
                <td className="dim">{Object.keys(e.details).length ? JSON.stringify(e.details) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
