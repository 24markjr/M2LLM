/**
 * The knowledge graph explorer (Phase 32): a mission's knowledge graph in 3D, interactive.
 *
 * What the user asked for, and where it is:
 * - **Hover a node** -> a pop-up with that node's information (`NodeTooltip`, details fetched once
 *   from `/knowledge/nodes/{id}` and cached).
 * - **Click a node** -> it and every related sub-node and neighbour light up, the rest dims, the
 *   camera flies to it, and the side panel opens (`highlightSet` in `model.ts`). The depth control
 *   sets how far "related" reaches.
 * - **Nodes with sub-nodes** -> an entity's claims and their documents unfold under it on double
 *   click, or from the panel's Expand button.
 * Added: conflicts drawn red with moving particles; click a finding to light up the evidence it
 * rests on; search to fly to an entity; filters; a 2D view, chosen automatically for reduced motion
 * or no WebGL; a keyboard-navigable list mirroring the graph; and live growth while a mission runs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../../api/client";
import type { GraphNode, KnowledgeGraphView, NodeDetail } from "../../api/types";
import { KnowledgeGraph3D } from "./KnowledgeGraph3D";
import type { Filters } from "./model";
import {
  NO_FILTERS,
  highlightSet,
  highlightedLinks,
  initialMode,
  listOrder,
  parentsToExpand,
  recallText,
  searchEntities,
  visibleGraph,
} from "./model";

/** Where the graph comes from: a mission (live, with details and trails) or an analysis. */
export type GraphSource = { kind: "mission"; runId: string } | { kind: "analysis"; view: KnowledgeGraphView };

const ENTITY_TYPES = ["PERSON", "ORG", "LOCATION", "DATE", "PRODUCT", "SHIPMENT", "OTHER"];
// Events after which the graph may have changed: the knowledge base was built, a finding settled,
// or the run ended.
const REFRESH_ON = ["KNOWLEDGE_EXTRACTED", "FINDING_VERIFIED", "FINDING_REJECTED"];

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export default function KnowledgeExplorer({ source }: { source: GraphSource }) {
  const runId = source.kind === "mission" ? source.runId : null;
  const [view, setView] = useState<KnowledgeGraphView | null>(
    source.kind === "analysis" ? source.view : null,
  );
  const [status, setStatus] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [trail, setTrail] = useState<{ findingId: string; ids: Set<string>; unmatched: string[] } | null>(null);
  const [mode, setMode] = useState<"2d" | "3d">(() => initialMode(prefersReducedMotion(), hasWebGL()));
  const [hover, setHover] = useState<{ node: GraphNode; x: number; y: number } | null>(null);
  const [query, setQuery] = useState("");
  const details = useRef(new Map<string, NodeDetail>());
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [hoverDetail, setHoverDetail] = useState<NodeDetail | null>(null);
  // Missions memory has seen an entity in, by name (Phase 33). null: memory could not answer.
  const recalled = useRef(new Map<string, string[] | null>());
  const [hoverRecall, setHoverRecall] = useState<string[] | null>(null);
  const [selectedRecall, setSelectedRecall] = useState<string[] | null>(null);

  // --- loading, and live growth while the mission runs --------------------------------------
  const load = useCallback(async () => {
    if (!runId) return;
    try {
      setView(await api.getKnowledgeGraph(runId));
      details.current.clear();
      setStatus(null);
    } catch (exc: unknown) {
      if (exc instanceof ApiError && exc.code === "KNOWLEDGE_NOT_BUILT") {
        setStatus({
          tone: "info",
          text: "This mission has no knowledge graph: its plan never asked for entities or claims, and the objective was not a comparison.",
        });
      } else if (exc instanceof ApiError && exc.isNotReady) {
        setStatus({ tone: "info", text: "The knowledge base is still being built. It will appear here when it is ready." });
      } else {
        setStatus({ tone: "error", text: exc instanceof Error ? exc.message : String(exc) });
      }
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    void load();
    const stream = new EventSource(api.streamUrl(runId));
    const refresh = () => void load();
    for (const kind of REFRESH_ON) stream.addEventListener(kind, refresh);
    stream.addEventListener("stream_closed", () => {
      stream.close();
      refresh();
    });
    return () => stream.close();
  }, [runId, load]);

  // --- what is visible and what is lit -------------------------------------------------------
  const lit = useMemo(() => {
    if (!view) return null;
    if (trail) return trail.ids;
    return selected ? highlightSet(view, selected, depth) : null;
  }, [view, trail, selected, depth]);

  const graph = useMemo(
    () => (view ? visibleGraph(view, expanded, filters) : { nodes: [], links: [] }),
    [view, expanded, filters],
  );
  const litLinks = useMemo(() => (lit ? highlightedLinks(graph.links, lit) : null), [graph, lit]);
  const ordered = useMemo(() => listOrder(graph), [graph]);
  const documents = useMemo(
    () => (view ? view.nodes.filter((n) => n.kind === "DOCUMENT").map((n) => n.label) : []),
    [view],
  );
  const findings = useMemo(() => (view ? view.nodes.filter((n) => n.kind === "FINDING") : []), [view]);

  // --- node details, fetched once each ------------------------------------------------------------
  const fetchDetail = useCallback(
    async (nodeId: string): Promise<NodeDetail | null> => {
      const cached = details.current.get(nodeId);
      if (cached) return cached;
      if (!runId) return null;
      try {
        const found = await api.getKnowledgeNode(runId, nodeId);
        details.current.set(nodeId, found);
        return found;
      } catch {
        return null;
      }
    },
    [runId],
  );

  useEffect(() => {
    setHoverDetail(null);
    setHoverRecall(null);
    if (!hover) return;
    let current = true;
    void fetchDetail(hover.node.id).then((d) => current && setHoverDetail(d));
    if (hover.node.kind === "ENTITY") void fetchRecall(hover.node.label).then((r) => current && setHoverRecall(r));
    return () => {
      current = false;
    };
  }, [hover, fetchDetail]);

  // The keyboard path gets the same: the selected entity's past, in its panel.
  useEffect(() => {
    setSelectedRecall(null);
    const node = selected && view ? view.nodes.find((n) => n.id === selected) : undefined;
    if (node?.kind !== "ENTITY") return;
    let current = true;
    void fetchRecall(node.label).then((r) => current && setSelectedRecall(r));
    return () => {
      current = false;
    };
  }, [selected, view]);

  /** Fetched once per name. A 404 means memory has no record (new); any other failure, unknown. */
  async function fetchRecall(name: string): Promise<string[] | null> {
    if (recalled.current.has(name)) return recalled.current.get(name) ?? null;
    let runs: string[] | null;
    try {
      runs = (await api.getEntityMemory(name)).entity.runs;
    } catch (exc: unknown) {
      runs = exc instanceof ApiError && exc.code === "MEMORY_NOT_FOUND" ? [] : null;
    }
    recalled.current.set(name, runs);
    return runs;
  }

  useEffect(() => {
    setDetail(null);
    if (!selected) return;
    let current = true;
    void fetchDetail(selected).then((d) => current && setDetail(d));
    return () => {
      current = false;
    };
  }, [selected, fetchDetail]);

  // --- gestures ------------------------------------------------------------------------------------
  const select = useCallback(
    (nodeId: string) => {
      setTrail(null);
      setSelected(nodeId);
      setFocus(nodeId);
      // A lit claim inside a collapsed entity should be seen: open its parent.
      if (view) {
        const opened = parentsToExpand(view, highlightSet(view, nodeId, depth));
        if (opened.size) setExpanded((current) => new Set([...current, ...opened]));
      }
    },
    [view, depth],
  );

  const toggleExpand = useCallback((nodeId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setSelected(null);
    setTrail(null);
    setFocus(null);
  }, []);

  const showTrail = useCallback(
    async (findingId: string) => {
      if (!runId || !view) return;
      try {
        const found = await api.getFindingTrail(runId, findingId);
        const ids = new Set(found.node_ids);
        setSelected(null);
        setTrail({ findingId, ids, unmatched: found.unmatched_sources });
        setExpanded((current) => new Set([...current, ...parentsToExpand(view, ids)]));
        setFilters((current) => ({ ...current, showFindings: true }));
        setFocus(findingId);
      } catch (exc: unknown) {
        setStatus({ tone: "error", text: exc instanceof Error ? exc.message : String(exc) });
      }
    },
    [runId, view],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") clear();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clear]);

  const search = (text: string) => {
    setQuery(text);
    if (!view) return;
    const [best] = searchEntities(view, text);
    if (best && best.label.toLowerCase() === text.trim().toLowerCase()) select(best.id);
  };

  const onListKey = (event: React.KeyboardEvent<HTMLUListElement>) => {
    if (!ordered.length) return;
    const index = Math.max(0, ordered.findIndex((n) => n.id === selected));
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next = ordered[(index + step + ordered.length) % ordered.length];
      if (next) select(next.id);
    } else if (event.key === "Enter" && selected) {
      const node = ordered[index];
      if (node?.kind === "ENTITY") toggleExpand(node.id);
    }
  };

  // --- rendering -----------------------------------------------------------------------------------
  if (!view) {
    return (
      <div className="panel">
        <h2>Knowledge graph</h2>
        <div className="empty">{status ? status.text : "Loading the knowledge graph."}</div>
      </div>
    );
  }

  return (
    <div className="explorer">
      {status ? <div className={`notice ${status.tone === "error" ? "error" : ""}`}>{status.text}</div> : null}

      <div className="explorer-controls">
        <input
          className="search"
          list="graph-entities"
          placeholder="Find an entity"
          value={query}
          onChange={(e) => search(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && view) {
              const [best] = searchEntities(view, query);
              if (best) select(best.id);
            }
          }}
          aria-label="Find an entity and fly to it"
        />
        <datalist id="graph-entities">
          {view.nodes
            .filter((n) => n.kind === "ENTITY")
            .map((n) => (
              <option key={n.id} value={n.label} />
            ))}
        </datalist>
        <label>
          depth{" "}
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))} aria-label="How far related reaches">
            {[1, 2, 3].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.conflictsOnly}
            onChange={(e) => setFilters({ ...filters, conflictsOnly: e.target.checked })}
          />{" "}
          conflicts only
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.groundedOnly}
            onChange={(e) => setFilters({ ...filters, groundedOnly: e.target.checked })}
          />{" "}
          grounded only
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.showFindings}
            onChange={(e) => setFilters({ ...filters, showFindings: e.target.checked })}
          />{" "}
          findings
        </label>
        <select
          value={filters.document ?? ""}
          onChange={(e) => setFilters({ ...filters, document: e.target.value || null })}
          aria-label="Only what is tied to one document"
        >
          <option value="">all documents</option>
          {documents.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <details className="types">
          <summary>types</summary>
          {ENTITY_TYPES.map((type) => (
            <label key={type}>
              <input
                type="checkbox"
                checked={filters.entityTypes.size === 0 || filters.entityTypes.has(type)}
                onChange={(e) => {
                  const next = new Set(filters.entityTypes.size ? filters.entityTypes : ENTITY_TYPES);
                  if (e.target.checked) next.add(type);
                  else next.delete(type);
                  setFilters({ ...filters, entityTypes: next.size === ENTITY_TYPES.length ? new Set() : next });
                }}
              />{" "}
              {type.toLowerCase()}
            </label>
          ))}
        </details>
        <span className="spacer" />
        <button onClick={() => setMode(mode === "3d" ? "2d" : "3d")}>{mode === "3d" ? "2D view" : "3D view"}</button>
        <button
          onClick={() => {
            clear();
            setExpanded(new Set());
            setFilters(NO_FILTERS);
          }}
        >
          Reset
        </button>
      </div>

      <div className="explorer-body">
        <div className="explorer-stage">
          <KnowledgeGraph3D
            graph={graph}
            lit={lit}
            litLinks={litLinks}
            selectedId={selected}
            focusId={focus}
            mode={mode}
            onHover={(node, x, y) => setHover(node ? { node, x, y } : null)}
            onClick={(node) => (node.kind === "FINDING" ? void showTrail(node.id) : select(node.id))}
            onDoubleClick={(node) => node.kind === "ENTITY" && toggleExpand(node.id)}
            onBackground={clear}
          />
          {hover ? (
            <NodeTooltip
              node={hover.node}
              detail={hoverDetail}
              recall={recallText(hoverRecall, runId)}
              x={hover.x}
              y={hover.y}
            />
          ) : null}
          <Legend />
          <div className="stage-hint dim mono">
            hover: details · click: light up related · double-click an entity: unfold its claims · Esc: clear
          </div>
        </div>

        <aside className="explorer-side">
          {trail ? (
            <div className="panel">
              <h2>Evidence trail</h2>
              <div className="panel-body">
                <div className="mono">{trail.findingId}</div>
                <div className="dim">{trail.ids.size} node(s) lit: the claims, documents and entities this finding rests on.</div>
                {trail.unmatched.length ? (
                  <div className="hint">
                    Cited lines with no extracted claim: <span className="mono">{trail.unmatched.join(", ")}</span>
                  </div>
                ) : null}
                <button onClick={clear}>Clear trail</button>
              </div>
            </div>
          ) : null}

          {selected ? (
            <NodePanel
              detail={detail}
              recall={recallText(selectedRecall, runId)}
              node={graph.nodes.find((n) => n.id === selected) ?? view.nodes.find((n) => n.id === selected) ?? null}
              expanded={expanded.has(selected)}
              onToggle={() => toggleExpand(selected)}
              onClear={clear}
            />
          ) : null}

          {findings.length ? (
            <div className="panel">
              <h2>
                Findings <span className="count">{findings.length}</span>
              </h2>
              <ul className="finding-trails">
                {findings.map((f) => (
                  <li key={f.id}>
                    <button
                      className={trail?.findingId === f.id ? "on" : ""}
                      onClick={() => void showTrail(f.id)}
                      title="Light up the evidence this finding rests on"
                    >
                      <span className="mono">{f.id}</span> <span className="dim">[{f.status || "unverified"}]</span> {f.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="panel">
            <h2>
              Nodes <span className="count">{ordered.length}</span>
            </h2>
            <ul className="node-list" role="listbox" tabIndex={0} onKeyDown={onListKey} aria-label="Graph nodes; arrow keys move, Enter unfolds an entity">
              {ordered.map((node) => (
                <li
                  key={node.id}
                  role="option"
                  aria-selected={node.id === selected}
                  className={`${node.id === selected ? "on" : ""} ${lit && !lit.has(node.id) ? "faded" : ""} kind-${node.kind.toLowerCase()}`}
                  onClick={() => select(node.id)}
                  onDoubleClick={() => node.kind === "ENTITY" && toggleExpand(node.id)}
                >
                  <span className="glyph" aria-hidden="true">
                    {GLYPH[node.kind]}
                  </span>{" "}
                  {node.label}
                  {node.conflict_count > 0 ? <span className="tag bad"> conflict</span> : null}
                  {node.kind === "CLAIM" && !node.grounded ? <span className="tag"> ungrounded</span> : null}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}

const GLYPH: Record<GraphNode["kind"], string> = { ENTITY: "●", CLAIM: "■", DOCUMENT: "◆", FINDING: "▲" };

function NodeTooltip({
  node,
  detail,
  recall,
  x,
  y,
}: {
  node: GraphNode;
  detail: NodeDetail | null;
  recall: string;
  x: number;
  y: number;
}) {
  return (
    <div className="node-tooltip" style={{ left: x + 14, top: y + 14 }} role="tooltip">
      <div className="tooltip-head">
        <span aria-hidden="true">{GLYPH[node.kind]}</span> {node.label}
      </div>
      <div className="dim mono">
        {node.kind.toLowerCase()}
        {node.entity_type ? ` · ${node.entity_type.toLowerCase()}` : ""}
      </div>
      {node.kind === "ENTITY" ? (
        <>
          <div>
            {node.claim_count} claim(s) · {node.conflict_count} conflict(s)
          </div>
          {detail?.entity?.aliases.length ? <div className="dim">also: {detail.entity.aliases.join(", ")}</div> : null}
          {detail ? <div className="dim">in: {detail.documents.join(", ")}</div> : null}
          {recall ? <div className="memory-note">{recall}</div> : null}
        </>
      ) : null}
      {node.kind === "CLAIM" ? (
        <>
          <div className="mono">{node.source}</div>
          {detail?.claims[0]?.quote ? <div className="quote">“{detail.claims[0].quote}”</div> : null}
          <div className="dim">{node.grounded ? "grounded on its line" : "UNGROUNDED: value not found on its line"}</div>
          {node.conflict_count ? <div className="bad">in a conflict</div> : null}
        </>
      ) : null}
      {node.kind === "DOCUMENT" && detail ? (
        <div>
          {detail.entities.length} entities · {detail.claims.length} claims
        </div>
      ) : null}
      {node.kind === "FINDING" ? <div>verification: {node.status || "none"} · click to light up its evidence</div> : null}
    </div>
  );
}

function NodePanel({
  node,
  detail,
  recall,
  expanded,
  onToggle,
  onClear,
}: {
  node: GraphNode | null;
  detail: NodeDetail | null;
  recall: string;
  expanded: boolean;
  onToggle: () => void;
  onClear: () => void;
}) {
  if (!node) return null;
  return (
    <div className="panel">
      <h2>
        <span aria-hidden="true">{GLYPH[node.kind]}</span> {node.label}
        <span className="count">{node.id}</span>
      </h2>
      <div className="panel-body">
        <div className="row">
          {node.kind === "ENTITY" ? <button onClick={onToggle}>{expanded ? "Collapse" : "Expand"}</button> : null}
          <button onClick={onClear}>Clear</button>
        </div>
        {node.kind === "ENTITY" && recall ? (
          <div className="memory-note">
            {recall} · <a href="#/memory">memory</a>
          </div>
        ) : null}
        {detail?.claims.length ? (
          <>
            <h3>Claims</h3>
            <ul className="detail-list">
              {detail.claims.map((c) => (
                <li key={c.claim_id}>
                  <span className="mono">{c.attribute}</span> = {c.value} <span className="dim mono">{c.source}</span>
                  {c.grounded ? null : <span className="tag"> ungrounded</span>}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {detail?.conflicts.length ? (
          <>
            <h3>Conflicts</h3>
            <ul className="detail-list">
              {detail.conflicts.map((k) => (
                <li key={k.conflict_id}>
                  <span className="bad">{k.attribute}</span>:{" "}
                  {k.sides.map((s) => `${s.value} (${s.sources.join(", ")})`).join(" vs ")}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {detail?.relationships.length ? (
          <>
            <h3>Relationships</h3>
            <ul className="detail-list">
              {detail.relationships.map((r) => (
                <li key={r.relationship_id} className="mono">
                  {r.subject_id} {r.predicate} {r.object_id}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {detail?.finding_claim ? <div>{detail.finding_claim}</div> : null}
        {detail === null && node.kind !== "ENTITY" ? <div className="dim">{node.source}</div> : null}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="legend" aria-label="Legend">
      <span>● entity</span>
      <span>■ claim</span>
      <span>◆ document</span>
      <span>▲ finding</span>
      <span className="bad">― conflict (moving)</span>
      <span className="ok">― cites</span>
    </div>
  );
}
