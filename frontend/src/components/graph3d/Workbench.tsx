/**
 * Member 3's investigation views beside the graph (Phase 36): hybrid search, the timeline, and
 * every contradiction. Their dashboard showed these as separate modes; here they are tabs on one
 * workbench, and every row leads somewhere (the owner's rule: everything is interrelated):
 *
 * - a search hit or a timeline event **selects its claim** in the graph (unfolding its entity);
 * - an entity name anywhere **opens that entity** (its investigate card, its node lit);
 * - a contradiction **lights up all of its sides** at once, like a finding's evidence trail;
 * - selecting an entity in the graph **narrows the timeline and the contradictions** to it, with
 *   a switch back to everything.
 */

import { useEffect, useState } from "react";

import type { ClaimComparison, ClaimConflict, SearchHit, TimelineEvent } from "../../api/types";
import type { KnowledgeAccess } from "./access";
import { conflictSpotlight, formatDate, orderLabel, relationLabel, togglePick } from "./investigation";

/** What a row can do. Shared by the workbench and the investigate card. */
export interface Links {
  selectNode: (nodeId: string) => void;
  openEntity: (entityId: string) => void;
  spotlight: (label: string, ids: Set<string>, focusId: string) => void;
  searchFor: (text: string) => void;
}

export type WorkbenchTab = "search" | "timeline" | "conflicts";

export function Workbench({
  access,
  version,
  focusEntity,
  lit,
  selectedId,
  depth,
  tab,
  onTab,
  query,
  onQuery,
  links,
}: {
  access: KnowledgeAccess;
  /** Bumped when the knowledge base changes, so the lists refetch. */
  version: number;
  focusEntity: { id: string; name: string } | null;
  lit: ReadonlySet<string> | null;
  selectedId: string | null;
  depth: number;
  tab: WorkbenchTab;
  onTab: (tab: WorkbenchTab) => void;
  query: string;
  onQuery: (text: string) => void;
  links: Links;
}) {
  const [allEntities, setAllEntities] = useState(false);
  const scope = focusEntity && !allEntities ? focusEntity.id : undefined;
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [conflicts, setConflicts] = useState<ClaimConflict[]>([]);

  useEffect(() => setAllEntities(false), [focusEntity?.id]);

  useEffect(() => {
    let current = true;
    void Promise.all([access.timeline(scope), access.conflicts(scope)])
      .then(([events, found]) => {
        if (!current) return;
        setTimeline(events);
        setConflicts(found);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [access, scope, version]);

  const active = (id: string) => id === selectedId || (lit?.has(id) ?? false);

  return (
    <div className="panel workbench">
      <div className="workbench-tabs" role="tablist" aria-label="Investigation views">
        {(
          [
            ["search", "Search"],
            ["timeline", `Timeline · ${timeline.length}`],
            ["conflicts", `Contradictions · ${conflicts.length}`],
          ] as const
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => onTab(id)}>
            {label}
          </button>
        ))}
        <span className="spacer" />
        {focusEntity && tab !== "search" ? (
          <label className="dim">
            <input type="checkbox" checked={allEntities} onChange={(e) => setAllEntities(e.target.checked)} /> all
            entities, not only <b>{focusEntity.name}</b>
          </label>
        ) : null}
      </div>
      <div className="panel-body">
        {tab === "search" ? (
          <SearchView access={access} version={version} depth={depth} query={query} onQuery={onQuery} active={active} links={links} />
        ) : null}
        {tab === "timeline" ? <TimelineView access={access} events={timeline} active={active} links={links} /> : null}
        {tab === "conflicts" ? <ConflictList conflicts={conflicts} lit={lit} links={links} /> : null}
      </div>
    </div>
  );
}

// --- hybrid search ------------------------------------------------------------------------------

function SearchView({
  access,
  version,
  depth,
  query,
  onQuery,
  active,
  links,
}: {
  access: KnowledgeAccess;
  version: number;
  depth: number;
  query: string;
  onQuery: (text: string) => void;
  active: (id: string) => boolean;
  links: Links;
}) {
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const text = query.trim();
    if (!text || !access.stored) {
      setHits(null);
      return;
    }
    let current = true;
    const timer = window.setTimeout(() => {
      access
        .search(text, depth)
        .then((found) => current && (setHits(found), setError("")))
        .catch((exc: unknown) => current && setError(exc instanceof Error ? exc.message : String(exc)));
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [access, query, depth, version]);

  if (!access.stored) {
    return (
      <div className="empty">
        Search ranks claims with Member 3's scoring on the server, so it needs a stored knowledge base: run these
        documents as a mission. The timeline and contradictions here work.
      </div>
    );
  }

  return (
    <>
      <input
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder='Free text, e.g. "Rahul warehouse" - no exact entity name needed'
        aria-label="Search claims"
      />
      {error ? <div className="notice error">{error}</div> : null}
      {hits && hits.length === 0 ? <div className="empty">No claim matches.</div> : null}
      <ol className="workbench-list">
        {hits?.map((hit) => (
          <li key={hit.claim.claim_id} className={active(hit.claim.claim_id) ? "on" : ""}>
            <button className="row-main" onClick={() => links.selectNode(hit.claim.claim_id)} title="Select this claim in the graph">
              <span className="score" aria-label={`score ${hit.score}`}>
                {hit.score}
              </span>
              <span className="mono">{hit.claim.attribute}</span> = {hit.claim.value}
            </button>
            <div className="row-meta">
              <button className="link" onClick={() => links.openEntity(hit.claim.entity_id)}>
                {hit.entity_name || hit.claim.entity_id}
              </button>
              <span className="dim mono">{hit.claim.source}</span>
              {hit.explanation.map((reason) => (
                <span key={reason} className="tag">
                  {reason}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

// --- timeline -----------------------------------------------------------------------------------

function TimelineView({
  access,
  events,
  active,
  links,
}: {
  access: KnowledgeAccess;
  events: TimelineEvent[];
  active: (id: string) => boolean;
  links: Links;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ClaimComparison | null>(null);

  useEffect(() => {
    setComparison(null);
    const [a, b] = picked;
    if (!a || !b || !access.stored) return;
    let current = true;
    void access
      .compare(a, b)
      .then((found) => current && setComparison(found))
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [access, picked]);

  if (!events.length) return <div className="empty">No dated claims.</div>;
  return (
    <>
      {access.stored ? (
        <div className="dim">
          Tick two events to compare them.
          {comparison ? (
            <span className="compare-result">
              {" "}
              {orderLabel(comparison.relation)}
              {comparison.reason ? ` (${comparison.reason})` : ""}.
            </span>
          ) : null}
        </div>
      ) : null}
      <ol className="workbench-list timeline">
        {events.map((event) => (
          <li key={event.claim_id} className={active(event.claim_id) ? "on" : ""}>
            {access.stored ? (
              <input
                type="checkbox"
                checked={picked.includes(event.claim_id)}
                onChange={() => setPicked(togglePick(picked, event.claim_id))}
                aria-label={`compare ${event.attribute} = ${event.value}`}
              />
            ) : null}
            <button className="row-main" onClick={() => links.selectNode(event.claim_id)} title="Select this claim in the graph">
              <span className="when mono">{formatDate(event.date, event.year_inferred)}</span>
              <span className="mono">{event.attribute}</span> = {event.value}
            </button>
            <div className="row-meta">
              <span className={`tag rel-${(event.relation_to_previous ?? "first").toLowerCase()}`}>
                {relationLabel(event.relation_to_previous)}
              </span>
              <button className="link" onClick={() => links.openEntity(event.entity_id)}>
                {event.entity_name}
              </button>
              <span className="dim mono">{event.source}</span>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

// --- every contradiction ------------------------------------------------------------------------

export function ConflictList({
  conflicts,
  lit,
  links,
}: {
  conflicts: ClaimConflict[];
  lit: ReadonlySet<string> | null;
  links: Links;
}) {
  if (!conflicts.length) return <div className="empty">No contradictions: no two sources gave different values for one attribute.</div>;
  return (
    <ol className="workbench-list">
      {conflicts.map((conflict) => {
        const on = conflict.sides.some((side) => side.claim_ids.some((id) => lit?.has(id)));
        return (
          <li key={conflict.conflict_id} className={on ? "on" : ""}>
            <button
              className="row-main"
              onClick={() =>
                links.spotlight(
                  `${conflict.entity_name}: ${conflict.attribute}`,
                  conflictSpotlight(conflict),
                  conflict.sides[0]?.claim_ids[0] ?? conflict.entity_id,
                )
              }
              title="Light up every side of this contradiction in the graph"
            >
              <span className="bad">conflict</span> <span className="mono">{conflict.attribute}</span>{" "}
              <span className="dim">({conflict.kind.toLowerCase()})</span>
            </button>
            <div className="row-meta">
              <button className="link" onClick={() => links.openEntity(conflict.entity_id)}>
                {conflict.entity_name}
              </button>
            </div>
            <ul className="sides">
              {conflict.sides.map((side) => (
                <li key={side.value}>
                  <button className="link" onClick={() => side.claim_ids[0] && links.selectNode(side.claim_ids[0])}>
                    {side.value}
                  </button>{" "}
                  <span className="dim mono">{side.sources.join(", ")}</span>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
