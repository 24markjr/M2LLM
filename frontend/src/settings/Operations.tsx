/**
 * Operating the organisation (v4 Phase 8), for its admins: what the investigations took and cost,
 * and the data governance - retention, masking, data-subject requests and the audit export.
 * The server enforces every rule; the page only shows them.
 */

import { useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { GovernancePolicy, OpsSummary, Packs, RetentionResult, SubjectReport } from "../api/types";
import { useUser } from "../auth/AuthGate";
import { Button, Notice, useToast } from "../ui/components";

function message(exc: unknown): string {
  return exc instanceof ApiError ? exc.message : "Something went wrong.";
}

const inr = (value: number) => `INR ${value.toFixed(2)}`;
const seconds = (value: number) => (value >= 60 ? `${(value / 60).toFixed(1)} min` : `${value.toFixed(0)} s`);

export function OperationsCard() {
  const { user } = useUser();
  const [days, setDays] = useState(7);
  const [ops, setOps] = useState<OpsSummary | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (user?.role !== "admin") return;
    api
      .opsMetrics(days)
      .then(setOps)
      .catch((exc: unknown) => setError(message(exc)));
  }, [user, days]);
  if (user?.role !== "admin") return null;

  return (
    <section className="settings-card" aria-labelledby="s-ops">
      <h2 id="s-ops">Operations</h2>
      <div className="settings-row">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
          <option value={1}>Last day</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>
        {ops ? (
          <span className="settings-note">
            Model {ops.model} {ops.model_healthy ? "answering" : "not answering"} · {ops.running} running, {ops.waiting} waiting
          </span>
        ) : null}
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {ops ? (
        <>
          <dl className="settings-facts">
            <dt>Investigations</dt>
            <dd>
              {ops.investigations} ({ops.completed} completed, {ops.failed} failed, {ops.cancelled} cancelled) · error rate{" "}
              {(ops.error_rate * 100).toFixed(1)}%
            </dd>
            <dt>Time</dt>
            <dd>
              median {seconds(ops.duration_p50_s)}, 95th percentile {seconds(ops.duration_p95_s)} · median wait in queue{" "}
              {seconds(ops.queue_wait_p50_s)}
            </dd>
            <dt>Model use</dt>
            <dd>
              {ops.llm_calls} calls, {ops.tokens.toLocaleString()} tokens
            </dd>
            <dt>Cost</dt>
            <dd>
              {inr(ops.cost_per_investigation_inr)} per investigation · {inr(ops.cost_total_inr)} in all - estimated at GPU{" "}
              {inr(ops.rates.gpu_per_hour_inr ?? 0)}/h and server {inr(ops.rates.server_per_hour_inr ?? 0)}/h
            </dd>
          </dl>
          {ops.recent_errors.length ? (
            <table className="settings-people">
              <thead>
                <tr>
                  <th>Failed investigation</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {ops.recent_errors.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <a href={`#/mission/${r.run_id}`}>{r.run_id}</a>
                    </td>
                    <td className="settings-note">{r.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export function GovernanceCard() {
  const { user } = useUser();
  const notify = useToast();
  const [policy, setPolicy] = useState<GovernancePolicy | null>(null);
  const [retention, setRetention] = useState<RetentionResult | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [subject, setSubject] = useState<SubjectReport | null>(null);
  const [packs, setPacks] = useState<Packs | null>(null);
  useEffect(() => {
    void api
      .packs()
      .then(setPacks)
      .catch(() => setPacks(null));
    if (user?.role === "admin") {
      api
        .governancePolicy()
        .then(setPolicy)
        .catch(() => setPolicy(null));
    }
  }, [user]);
  if (user?.role !== "admin" || !policy) return null;

  const save = async (next: GovernancePolicy) => {
    try {
      setPolicy(await api.saveGovernancePolicy(next));
      notify("Policy saved.", "success");
    } catch (exc) {
      notify(message(exc), "error");
    }
  };
  const search = async (e: FormEvent) => {
    e.preventDefault();
    try {
      setSubject(await api.subjectSearch(identifier.trim()));
    } catch (exc) {
      notify(message(exc), "error");
    }
  };
  const erase = async () => {
    if (!subject) return;
    try {
      setSubject(await api.subjectErase(subject.identifier));
      notify("Erased. The evidence files listed are kept for a legal-hold decision.", "success");
    } catch (exc) {
      notify(message(exc), "error");
    }
  };

  return (
    <section className="settings-card" aria-labelledby="s-gov">
      <h2 id="s-gov">Data governance</h2>
      <div className="settings-row">
        <label>
          Keep investigations for{" "}
          <input
            type="number"
            min={0}
            max={3650}
            value={policy.retention_days}
            onChange={(e) => setPolicy({ ...policy, retention_days: Number(e.target.value) })}
            style={{ width: 80 }}
          />{" "}
          days (0 = until deleted)
        </label>
        <label>
          <input
            type="checkbox"
            checked={policy.mask_personal_data}
            onChange={(e) => setPolicy({ ...policy, mask_personal_data: e.target.checked })}
          />{" "}
          Mask e-mail, phone, Aadhaar, PAN and card numbers in exported reports
        </label>
        {packs ? (
          <label>
            Domain pack{" "}
            <select value={policy.pack} onChange={(e) => setPolicy({ ...policy, pack: e.target.value })}>
              {packs.packs.map((p) => (
                <option key={p.id} value={p.id} title={p.description}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <Button size="sm" onClick={() => void save(policy)}>
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void api.applyRetention(true).then(setRetention)}>
          What would retention delete?
        </Button>
      </div>
      {retention ? (
        <p className="settings-note">
          {retention.retention_days
            ? `${retention.deleted.length} investigation(s) older than ${retention.retention_days} days ${retention.dry_run ? "would be" : "were"} deleted. Evidence and its custody are kept.`
            : "Retention is off: nothing is deleted on a timer."}
        </p>
      ) : null}
      <form className="settings-row settings-add" onSubmit={(e) => void search(e)}>
        <input
          placeholder="A person's name, e-mail or ID (data-subject request)"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          minLength={3}
          required
        />
        <Button size="sm" type="submit">
          Find
        </Button>
        <a className="ui-button ghost sm" href={api.auditCsvUrl()}>
          Export audit log (CSV)
        </a>
      </form>
      {subject ? (
        <div className="settings-note">
          <p>
            "{subject.identifier}" appears {subject.hits.length} time(s): {subject.investigations.length} investigation(s),{" "}
            {subject.conversations.length} case conversation(s), in the files {subject.evidence_files.join(", ") || "none"}.
          </p>
          {subject.erased ? (
            <Notice tone="success">Erased. Evidence files are kept for a legal-hold decision.</Notice>
          ) : subject.hits.length ? (
            <Button size="sm" variant="secondary" onClick={() => void erase()}>
              Erase it (deletes those investigations, blanks those messages)
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
