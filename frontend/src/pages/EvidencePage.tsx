/**
 * The Evidence Locker (Phase 43): every input as an evidence item with its chain of custody.
 *
 * The list shows what is held - identity (EV number and SHA-256), integrity, classification, where it
 * came from, and how many findings rest on it. An item's page shows its full custody, append-only,
 * the findings that cited it (each a link to its mission), other versions under the same name, a
 * re-verify button and the original for download. A finding's citation links here, so any finding
 * is two clicks from the history of the bytes it rests on.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { AuthorityTier, EvidenceDetail, IntegrityCheck } from "../api/types";
import {
  CLASSIFICATIONS,
  authorityWords,
  custodyLabel,
  custodySummary,
  evidenceLink,
} from "../components/evidence";
import { sizeLabel } from "../components/documents";
import { shortHash } from "../components/workspaces";

function errorText(exc: unknown): string {
  return exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc);
}

function LockerNote({ locker }: { locker: string }) {
  return locker === "memory" ? (
    <div className="notice warn">
      The database is not reachable: this locker is held in memory, and custody recorded now is lost when
      the engine restarts. Start it with <code>docker compose up -d postgres</code>.
    </div>
  ) : null;
}

export function EvidenceItemPage({ evidenceId }: { evidenceId: string }) {
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [check, setCheck] = useState<IntegrityCheck | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .getEvidence(evidenceId)
      .then(setDetail)
      .catch((exc: unknown) => setError(errorText(exc)));
  }, [evidenceId]);

  useEffect(load, [load]);

  const verify = () => {
    setBusy(true);
    api
      .verifyEvidence(evidenceId)
      .then((result) => {
        setCheck(result);
        load();
      })
      .catch((exc: unknown) => setError(errorText(exc)))
      .finally(() => setBusy(false));
  };

  const [tiers, setTiers] = useState<AuthorityTier[]>([]);
  useEffect(() => {
    api
      .authorityTiers()
      .then(setTiers)
      .catch(() => setTiers([]));
  }, []);

  const weigh = (authority: string) => {
    const reason = window.prompt("Why this authority? (recorded in the chain of custody)") ?? "";
    api
      .updateEvidence(evidenceId, { authority, authority_reason: reason })
      .then(load)
      .catch((exc: unknown) => setError(errorText(exc)));
  };

  const classify = (classification: string) => {
    api
      .updateEvidence(evidenceId, { classification })
      .then(load)
      .catch((exc: unknown) => setError(errorText(exc)));
  };

  if (error && !detail) return <div className="notice error">{error}</div>;
  if (!detail) return <div className="empty">Loading {evidenceId}.</div>;
  const { item } = detail;

  return (
    <>
      <div className="row" style={{ marginBottom: 20 }}>
        <a className="button" href={evidenceLink()}>
          &larr; Evidence Locker
        </a>
        <span className="spacer" />
        <a className="button" href={api.evidenceDownloadUrl(item.evidence_id)}>
          Download original
        </a>
        <button onClick={verify} disabled={busy}>
          {busy ? "Verifying." : "Re-verify integrity"}
        </button>
      </div>
      <LockerNote locker={detail.locker} />
      {error ? <div className="notice error">{error}</div> : null}
      {check ? (
        <div className={`notice ${check.integrity === "FAILED" ? "error" : ""}`}>
          {check.integrity === "FAILED"
            ? `Integrity FAILED: ${check.reason}. It is left out of new missions; findings that cited it are listed below.`
            : "Integrity verified: the stored original (and the working copy missions read) match the recorded hash."}
        </div>
      ) : null}

      <div className="panel">
        <h2>
          {item.evidence_id} <span className="count">{item.name}</span>
        </h2>
        <div className="panel-body">
          <dl className="facts">
            <dt>SHA-256</dt>
            <dd className="mono">{item.sha256}</dd>
            <dt>Integrity</dt>
            <dd>
              <span className={`integrity ${item.integrity.toLowerCase()}`}>{item.integrity}</span>
              {item.integrity_checked_at ? (
                <span className="dim"> · checked {new Date(item.integrity_checked_at).toLocaleString()}</span>
              ) : null}
            </dd>
            <dt>Kind</dt>
            <dd>
              {item.kind || "-"} {item.parser ? <span className="dim">· read by {item.parser}</span> : null} ·{" "}
              {sizeLabel(item.bytes)}
            </dd>
            <dt>Collected</dt>
            <dd>
              {new Date(item.collected_at).toLocaleString()} by {item.collected_by}
              {item.source ? <span className="dim"> · {item.source}</span> : null}
            </dd>
            <dt>Classification</dt>
            <dd>
              <select
                aria-label="Classification"
                value={item.classification}
                onChange={(e) => classify(e.target.value)}
              >
                {CLASSIFICATIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>{" "}
              <span className="dim">a change is recorded in the custody below</span>
            </dd>
            <dt>Source authority</dt>
            <dd>
              <select
                aria-label="Source authority"
                value={item.authority ?? "UNASSESSED"}
                onChange={(e) => weigh(e.target.value)}
              >
                {(tiers.length
                  ? tiers.map((t) => ({ id: t.id, label: t.label }))
                  : [{ id: item.authority ?? "UNASSESSED", label: authorityWords(item.authority) }]
                ).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>{" "}
              <span className="dim">
                {item.authority_reason || "not assessed"} · shown on both sides of a contradiction, never used to
                settle one
              </span>
            </dd>
          </dl>
        </div>
      </div>

      <div className="panel">
        <h2>
          Cited by <span className="count">{detail.citations.length} finding(s)</span>
        </h2>
        <div className="panel-body">
          {detail.citations.length ? (
            detail.citations.map((c) => (
              <div key={`${c.run_id}:${c.finding_id}:${c.locator}`} className="evidence-row">
                <a className="mono" href={`#/mission/${c.run_id}`}>
                  {c.run_id} · {c.finding_id}
                </a>
                <span className="mono dim">{c.locator}</span>
                <span>{c.claim}</span>
                {item.integrity === "FAILED" ? <span className="integrity failed">rests on failed evidence</span> : null}
              </div>
            ))
          ) : (
            <div className="dim">No finding has cited this item yet.</div>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>
          Chain of custody <span className="count">{detail.custody.length} event(s), append-only</span>
        </h2>
        <div className="panel-body">
          <ol className="custody">
            {detail.custody.map((event) => (
              <li key={event.event_id} className={event.action === "INTEGRITY_FAILED" ? "failed" : ""}>
                <span className="mono dim">{new Date(event.at).toLocaleString()}</span>{" "}
                <strong>{custodyLabel(event.action)}</strong>{" "}
                <span className="dim">by {event.actor}</span>
                {custodySummary(event.action, event.details) ? (
                  <div className="dim">{custodySummary(event.action, event.details)}</div>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      </div>

      {detail.versions.length ? (
        <div className="panel">
          <h2>
            Other versions of {item.name} <span className="count">{detail.versions.length}</span>
          </h2>
          <div className="panel-body">
            {detail.versions.map((v) => (
              <div key={v.evidence_id} className="evidence-row">
                <a className="mono" href={evidenceLink(v.evidence_id)}>
                  {v.evidence_id}
                </a>
                <span className="mono dim">{shortHash(v.sha256)}</span>
                <span className="dim">{new Date(v.collected_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
