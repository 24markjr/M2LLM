/**
 * The shell and its routing.
 *
 * Hash routing, deliberately: this app is served as static files next to an API, sometimes
 * from a file path, and a history-API router needs a server that rewrites unknown paths to
 * index.html. A hash works everywhere and a mission URL stays shareable.
 */

import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import type { MissionDetail } from "./api/types";
import {
  EvaluationPage,
  MissionDetailPage,
  MissionList,
  NewMission,
  ReplayPage,
} from "./pages/pages";
import { MemoryPage } from "./pages/MemoryPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { CasePage, CasesPage } from "./pages/CasesPage";
import { caseIdFromHash } from "./components/cases";
import { EvidenceItemPage, EvidenceLockerPage } from "./pages/EvidencePage";
import { evidenceIdFromHash } from "./components/evidence";
import { draftFromHash } from "./components/workspaces";
import { hashQuery } from "./components/graph3d/investigation";

// The knowledge graph pages pull in three.js (~600 kB). Loaded only when opened (Phase 32).
const KnowledgeExplorer = lazy(() => import("./components/graph3d/KnowledgeExplorer"));
const AnalyzePage = lazy(() => import("./components/graph3d/AnalyzePage"));

type Route =
  | { name: "cases" }
  | { name: "case"; caseId: string }
  | { name: "list" }
  | { name: "new"; key: string }
  | { name: "documents"; workspace: string }
  | { name: "evidence"; evidenceId: string }
  | { name: "mission"; runId: string }
  | { name: "graph"; runId: string; focus: string; search: string }
  | { name: "knowledge" }
  | { name: "memory"; entity: string }
  | { name: "replay" }
  | { name: "evaluation" };

function parse(full: string): Route {
  // Pages link to each other with a parameter (Phase 36): the graph opened on an entity
  // (`?focus=`), Memory opened on an entity (`?entity=`).
  const query = hashQuery(full);
  const hash = full.split("?")[0] ?? full;
  const graph = /^#\/mission\/([\w-]+)\/graph$/.exec(hash);
  if (graph?.[1]) return { name: "graph", runId: graph[1], focus: query.focus ?? "", search: query.q ?? "" };
  if (hash === "#/knowledge") return { name: "knowledge" };
  if (hash === "#/memory") return { name: "memory", entity: query.entity ?? "" };
  const match = /^#\/mission\/([\w-]+)$/.exec(hash);
  if (match?.[1]) return { name: "mission", runId: match[1] };
  // New Mission may arrive filled in, from a search hit or a workspace (Phase 40).
  if (hash === "#/new") return { name: "new", key: full };
  if (hash === "#/evidence" || evidenceIdFromHash(hash)) {
    return { name: "evidence", evidenceId: evidenceIdFromHash(hash) };
  }
  if (hash === "#/documents") return { name: "documents", workspace: query.workspace ?? "default" };
  if (hash === "#/replay") return { name: "replay" };
  if (hash === "#/evaluation") return { name: "evaluation" };
  // Cases are the home page (Phase 44); the flat list of every investigation is `#/missions`.
  if (caseIdFromHash(hash)) return { name: "case", caseId: caseIdFromHash(hash) };
  if (hash === "#/missions") return { name: "list" };
  return { name: "cases" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  const [engine, setEngine] = useState<{ model: string; healthy: boolean } | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    const onHash = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    api
      .health()
      .then((body) => setEngine({ model: body.model, healthy: body.provider_healthy }))
      .catch(() => setUnreachable(true));
  }, []);

  const go = useCallback((hash: string) => {
    window.location.hash = hash;
  }, []);

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          JARVIS<span>//</span>MISSION CONTROL
        </div>
        <nav className="nav">
          <a className={route.name === "cases" || route.name === "case" ? "on" : ""} href="#/">
            Cases
          </a>
          <a className={route.name === "list" ? "on" : ""} href="#/missions">
            Missions
          </a>
          <a className={route.name === "replay" ? "on" : ""} href="#/replay">
            Replay
          </a>
          <a className={route.name === "evaluation" ? "on" : ""} href="#/evaluation">
            Evaluation
          </a>
          <a className={route.name === "knowledge" ? "on" : ""} href="#/knowledge">
            Knowledge
          </a>
          <a className={route.name === "documents" ? "on" : ""} href="#/documents">
            Documents
          </a>
          <a className={route.name === "evidence" ? "on" : ""} href="#/evidence">
            Evidence
          </a>
          <a className={route.name === "memory" ? "on" : ""} href="#/memory">
            Memory
          </a>
        </nav>
        <div className="tagline">adaptive, evidence-driven investigation</div>
        <div className="engine">
          <span
            className={`dot ${unreachable ? "down" : engine?.healthy ? "up" : ""}`}
            aria-hidden="true"
          />
          {unreachable ? "engine unreachable" : engine ? engine.model : "checking."}
        </div>
      </header>

      {unreachable ? (
        <div className="notice error">
          Cannot reach the engine. Start it from <code className="mono">backend/</code> with:
          <br />
          <code className="mono">uvicorn app.api.app:create_app --factory --reload</code>
        </div>
      ) : null}

      {route.name === "cases" ? <CasesPage /> : null}
      {route.name === "case" ? <CasePage key={route.caseId} caseId={route.caseId} /> : null}

      {route.name === "list" ? (
        <MissionList
          onOpen={(runId) => go(`#/mission/${runId}`)}
          onNew={() => go("#/new")}
        />
      ) : null}

      {route.name === "new" ? (
        <NewMission
          key={route.key}
          draft={draftFromHash(route.key)}
          onStarted={(mission: MissionDetail) => go(`#/mission/${mission.run_id}`)}
          onCancel={() => go("#/")}
        />
      ) : null}

      {route.name === "mission" ? (
        <MissionDetailPage runId={route.runId} onBack={() => go("#/missions")} />
      ) : null}

      {route.name === "replay" ? <ReplayPage onBack={() => go("#/")} /> : null}

      {route.name === "evaluation" ? <EvaluationPage onBack={() => go("#/")} /> : null}

      {route.name === "graph" ? (
        <>
          <div className="row" style={{ marginBottom: 20 }}>
            <button onClick={() => go(`#/mission/${route.runId}`)}>&larr; Mission</button>
            <span className="spacer" />
            <span className="dim mono">knowledge graph · {route.runId}</span>
          </div>
          <Suspense fallback={<div className="empty">Loading the 3D view.</div>}>
            <KnowledgeExplorer
              key={`${route.runId}:${route.focus}:${route.search}`}
              source={{ kind: "mission", runId: route.runId }}
              focusName={route.focus}
              initialSearch={route.search}
            />
          </Suspense>
        </>
      ) : null}

      {route.name === "knowledge" ? (
        <Suspense fallback={<div className="empty">Loading.</div>}>
          <AnalyzePage />
        </Suspense>
      ) : null}

      {route.name === "documents" ? <DocumentsPage key={route.workspace} workspace={route.workspace} /> : null}

      {route.name === "evidence" ? (
        route.evidenceId ? (
          <EvidenceItemPage key={route.evidenceId} evidenceId={route.evidenceId} />
        ) : (
          <EvidenceLockerPage />
        )
      ) : null}

      {route.name === "memory" ? <MemoryPage key={route.entity} entity={route.entity} /> : null}
    </div>
  );
}
