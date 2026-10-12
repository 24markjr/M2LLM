/**
 * The attack path in the 3D explorer (Phase 53): hosts, accounts and processes; observed steps
 * (blue), inferred steps (amber, each labelled "inferred ...: why"), and the ATT&CK techniques the
 * rules mapped to the hosts (purple). Inferred steps are never drawn as observed ones.
 */

import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { KnowledgeGraphView, KnowledgeSnapshot } from "../../api/types";
import KnowledgeExplorer from "./KnowledgeExplorer";

const EMPTY: KnowledgeSnapshot = { entities: [], relationships: [], claims: [], conflicts: [] };

export default function AttackGraphPage({ runId }: { runId: string }) {
  const [view, setView] = useState<KnowledgeGraphView | null>(null);
  const [error, setError] = useState("");
  // One snapshot object for the page's life: the explorer keys its data on it.
  const snapshot = useMemo(() => ({ ...EMPTY }), []);

  useEffect(() => {
    api
      .getAttackGraph(runId)
      .then(setView)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  }, [runId]);

  if (error) return <div className="notice error">{error}</div>;
  if (!view) return <div className="empty">Loading the attack path.</div>;
  if (view.nodes.length === 0) {
    return <div className="empty">This mission's documents hold no security events.</div>;
  }
  return (
    <>
      <div className="hint">
        Blue: observed steps. Amber: inferred steps, each with its reason. Purple: ATT&amp;CK
        techniques mapped by rule - every one needs an analyst&apos;s validation.
      </div>
      <KnowledgeExplorer source={{ kind: "analysis", view, snapshot, timeline: [] }} />
    </>
  );
}
