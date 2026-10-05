/**
 * Memory across investigations (Phase 33): Member 4's episodic and semantic memory, for people.
 *
 * Episodes: every finding of every stored mission, searchable, each with its verification status
 * (rejected ones included). Entities: one name as seen across missions, with the facts verified
 * findings cited about it and how many separate (mission, line) citations support each.
 *
 * Nothing here feeds a running mission; memory is read by people only.
 */

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { graphLink } from "../components/graph3d/investigation";
import type { EntityMemory, Episode, MemoryStatus } from "../api/types";

export function MemoryPage({ entity = "" }: { entity?: string }) {
  const [status, setStatus] = useState<MemoryStatus | null>(null);

  useEffect(() => {
    api
      .getMemoryStatus()
      .then(setStatus)
      .catch(() => setStatus({ episodic: false, semantic_store: "" }));
  }, []);

  return (
    <>
      <div className="panel">
        <h2>Memory</h2>
        <div className="panel-body">
          <div className="dim">
            What earlier missions found, kept after they finished. Episodes are every finding, with its
            verification status. Facts come only from findings that passed verification, and carry the
            number of separate citations behind them instead of a confidence. Memory is never fed back
            into a mission.
          </div>
          {status ? (
            <div className="mono dim" style={{ marginTop: 8 }}>
              episodes: {status.episodic ? "on (postgres)" : "off"} · facts:{" "}
              {status.semantic_store ? `on (${status.semantic_store})` : "off"}
            </div>
          ) : null}
        </div>
      </div>
      {status && !status.episodic && !status.semantic_store ? (
        <div className="notice warn">
          Memory is off: no store is reachable. Start them with <code>docker compose up -d</code> and
          run a mission.
        </div>
      ) : null}
      {status?.semantic_store ? <EntityLookup initial={entity} /> : null}
      {status?.episodic ? <EpisodeSearch /> : null}
    </>
  );
}

function EpisodeSearch() {
  const [query, setQuery] = useState("");
  const [episodes, setEpisodes] = useState<Episode[] | null>(null);
  const [error, setError] = useState("");

  const search = (q: string) => {
    setError("");
    api
      .searchEpisodes(q)
      .then(setEpisodes)
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  useEffect(() => search(""), []);

  // Remove what one mission contributed to memory (its episodes, its support for facts). The
  // mission itself and its recording are untouched.
  const forget = (runId: string) => {
    if (!window.confirm(`Remove ${runId} from memory? Its episodes go, and facts only it supported.`)) return;
    api
      .forgetRun(runId)
      .then(() => search(query))
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : String(exc)));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    search(query);
  };

  return (
    <div className="panel">
      <h2>
        Episodes {episodes ? <span className="count">{episodes.length}</span> : null}
      </h2>
      <div className="panel-body">
        <form className="row" onSubmit={submit}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search objectives and findings, e.g. shipment 4821"
            aria-label="Search episodes"
          />
          <button className="primary" type="submit">
            Search
          </button>
        </form>
        {error ? <div className="notice error">{error}</div> : null}
        {episodes && episodes.length === 0 ? <div className="empty">No episodes match.</div> : null}
        <ul className="memory-list">
          {episodes?.map((e) => (
            <li key={e.episode_id}>
              <div className="badges">
                <span className={`badge v-${e.verification_status.toLowerCase()}`}>{e.verification_status}</span>
                <a className="mono" href={`#/mission/${e.run_id}`}>
                  {e.run_id}
                </a>
                <span className="dim mono">{new Date(e.created_at).toLocaleString()}</span>
                <button className="link" onClick={() => forget(e.run_id)} title="Remove this mission from memory">
                  forget this mission
                </button>
              </div>
              <div>{e.claim}</div>
              <div className="dim">asked: {e.objective}</div>
              {e.sources.length ? <div className="mono dim">{e.sources.join(" · ")}</div> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function EntityLookup({ initial }: { initial: string }) {
  const [name, setName] = useState(initial);
  const [found, setFound] = useState<EntityMemory | null>(null);
  const [message, setMessage] = useState("");

  // Arriving from the graph with an entity (`#/memory?entity=`): look it up straight away.
  useEffect(() => {
    if (initial.trim()) find(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on arrival
  }, []);

  const lookup = (event: FormEvent) => {
    event.preventDefault();
    find(name);
  };

  const find = (raw: string) => {
    const wanted = raw.trim();
    if (!wanted) return;
    setFound(null);
    setMessage("");
    api
      .getEntityMemory(wanted)
      .then(setFound)
      .catch((exc: unknown) =>
        setMessage(
          exc instanceof ApiError && exc.code === "MEMORY_NOT_FOUND"
            ? `No earlier mission recorded "${wanted}".`
            : exc instanceof Error
              ? exc.message
              : String(exc),
        ),
      );
  };

  return (
    <div className="panel">
      <h2>Entity across missions</h2>
      <div className="panel-body">
        <form className="row" onSubmit={lookup}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="A person, organisation, shipment... e.g. Rahul Sharma"
            aria-label="Entity name"
          />
          <button className="primary" type="submit">
            Look up
          </button>
        </form>
        {message ? <div className="empty">{message}</div> : null}
        {found ? <EntityCard memory={found} /> : null}
      </div>
    </div>
  );
}

function EntityCard({ memory }: { memory: EntityMemory }) {
  const { entity, facts } = memory;
  return (
    <div className="memory-entity">
      <h3>
        {entity.name}{" "}
        <span className="dim mono">{entity.entity_types.map((t) => t.toLowerCase()).join(", ")}</span>
      </h3>
      {entity.aliases.length ? <div className="dim">also: {entity.aliases.join(", ")}</div> : null}
      <div>
        seen in {entity.runs.length} mission(s):{" "}
        {entity.runs.map((run, i) => (
          <span key={run}>
            {i ? ", " : ""}
            <a className="mono" href={`#/mission/${run}`}>
              {run}
            </a>{" "}
            <a href={graphLink(run, entity.name)} title={`Open ${run}'s knowledge graph on ${entity.name}`}>
              (graph)
            </a>
          </span>
        ))}
      </div>
      {facts.length === 0 ? (
        <div className="empty">No verified facts about it yet: no finding that passed verification cited it.</div>
      ) : (
        <div className="table-scroll">
          <table className="metrics memory-facts">
            <thead>
              <tr>
                <th>Fact</th>
                <th>Support</th>
                <th>Cited from</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((f) => (
                <tr key={f.fact_id}>
                  <td>
                    {f.subject} <span className="mono">{f.predicate}</span> {f.object}
                  </td>
                  <td className="num" title="separate (mission, line) citations">
                    {f.support_count}
                  </td>
                  <td className="mono dim">
                    {f.support.map((s) => `${s.run_id} ${s.source}`).join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
