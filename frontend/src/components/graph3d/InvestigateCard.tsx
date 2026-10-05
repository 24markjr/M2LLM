/**
 * An entity's investigate card (Phase 36): Member 3's `/investigation/{name}` - their dashboard's
 * main view - as the side panel for a selected entity.
 *
 * Everything on it leads somewhere (everything is interrelated): a document lights its node, a
 * claim selects it, a contradiction lights all of its sides, a timeline event selects its claim, a
 * connection opens that entity's card, "search" fills the workbench's search, and the memory line
 * opens the entity across past missions.
 */

import { useEffect, useState } from "react";

import type { EntityInvestigation, GraphNode, TimelineEvent } from "../../api/types";
import type { KnowledgeAccess } from "./access";
import type { Links } from "./Workbench";
import { conflictSpotlight, documentNodeId, formatDate, memoryLink, neighbourName, relationLabel } from "./investigation";

export function InvestigateCard({
  node,
  access,
  version,
  recall,
  expanded,
  onToggle,
  onClear,
  links,
}: {
  node: GraphNode;
  access: KnowledgeAccess;
  version: number;
  recall: string;
  expanded: boolean;
  onToggle: () => void;
  onClear: () => void;
  links: Links;
}) {
  const [found, setFound] = useState<EntityInvestigation | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setFound(null);
    setError("");
    void Promise.all([access.investigate(node.label), access.timeline(node.id)])
      .then(([investigation, events]) => {
        if (!current) return;
        setFound(investigation);
        setTimeline(events);
      })
      .catch((exc: unknown) => current && setError(exc instanceof Error ? exc.message : String(exc)));
    return () => {
      current = false;
    };
  }, [access, node.id, node.label, version]);

  return (
    <div className="panel investigate">
      <h2>
        <span aria-hidden="true">●</span> {node.label}
        <span className="count">{node.entity_type?.toLowerCase() ?? node.id}</span>
      </h2>
      <div className="panel-body">
        <div className="row">
          <button onClick={onToggle}>{expanded ? "Collapse" : "Expand"}</button>
          <button onClick={() => links.searchFor(node.label)} title="Search every claim for this name">
            Search
          </button>
          <button onClick={onClear}>Clear</button>
        </div>
        <div className="memory-note">
          {recall ? `${recall} · ` : ""}
          <a href={memoryLink(node.label)}>memory across missions</a>
        </div>
        {found?.entity.aliases.length ? <div className="dim">also: {found.entity.aliases.join(", ")}</div> : null}
        {error ? <div className="notice error">{error}</div> : null}
        {!found && !error ? <div className="dim">Investigating.</div> : null}

        {found ? (
          <>
            <Section title="Mentioned in" count={found.sources.length}>
              {found.sources.map((doc) => (
                <li key={doc}>
                  <button className="link mono" onClick={() => links.selectNode(documentNodeId(doc))}>
                    {doc}
                  </button>
                </li>
              ))}
            </Section>

            <Section title="Contradictions" count={found.conflicts.length} bad>
              {found.conflicts.map((conflict) => (
                <li key={conflict.conflict_id}>
                  <button
                    className="link"
                    onClick={() =>
                      links.spotlight(
                        `${conflict.entity_name}: ${conflict.attribute}`,
                        conflictSpotlight(conflict),
                        conflict.sides[0]?.claim_ids[0] ?? node.id,
                      )
                    }
                  >
                    <span className="bad">{conflict.attribute}</span>
                  </button>
                  : {conflict.sides.map((side) => `${side.value} (${side.sources.join(", ")})`).join(" vs ")}
                </li>
              ))}
            </Section>

            <Section title="Claims" count={found.claims.length}>
              {found.claims.map((claim) => (
                <li key={claim.claim_id}>
                  <button className="link" onClick={() => links.selectNode(claim.claim_id)}>
                    <span className="mono">{claim.attribute}</span> = {claim.value}
                  </button>{" "}
                  <span className="dim mono">{claim.source}</span>
                  {claim.grounded ? null : <span className="tag"> ungrounded</span>}
                </li>
              ))}
            </Section>

            <Section title="Timeline" count={timeline.length}>
              {timeline.map((event) => (
                <li key={event.claim_id}>
                  <button className="link" onClick={() => links.selectNode(event.claim_id)}>
                    <span className="mono">{formatDate(event.date, event.year_inferred)}</span> {event.attribute}
                  </button>{" "}
                  <span className="tag">{relationLabel(event.relation_to_previous)}</span>
                </li>
              ))}
            </Section>

            <Section title="Connections" count={found.network.edges.length}>
              {found.network.edges.map((edge) => {
                const outgoing = edge.from_id === found.entity.entity_id;
                const other = outgoing ? edge.to_id : edge.from_id;
                return (
                  <li key={`${edge.from_id}-${edge.predicate}-${edge.to_id}`}>
                    {outgoing ? "" : "← "}
                    <span className="mono">{edge.predicate}</span>
                    {outgoing ? " → " : " "}
                    <button className="link" onClick={() => links.openEntity(other)}>
                      {neighbourName(found, other)}
                    </button>
                  </li>
                );
              })}
            </Section>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Section({
  title,
  count,
  bad = false,
  children,
}: {
  title: string;
  count: number;
  bad?: boolean;
  children: React.ReactNode;
}) {
  if (!count) return null;
  return (
    <>
      <h3 className={bad ? "bad" : ""}>
        {title} <span className="count">{count}</span>
      </h3>
      <ul className="detail-list">{children}</ul>
    </>
  );
}
