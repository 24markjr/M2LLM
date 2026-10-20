/**
 * The pages, inside the application shell (Phase U3).
 *
 * Routing is in `shell/routes.ts`; the sidebar, top bar and search are in `shell/`. The pages
 * themselves are unchanged here and are replaced one by one from U4.
 */

import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import type { MissionDetail } from "./api/types";
import { HomePage } from "./home/HomePage";
import { JournalPage } from "./journal/JournalPage";
import { RecordingsPage, ReplayJournal } from "./journal/RecordingsPage";
import { AuditPage } from "./pages/AuditPage";
import { CasePage, CasesPage } from "./pages/CasesPage";
import { DesignPage } from "./pages/DesignPage";
import { SettingsPage } from "./settings/SettingsPage";
import { BenchmarkPanel } from "./components/BenchmarkPanel";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvidenceItemPage } from "./pages/EvidencePage";
import { LibraryPage } from "./library/LibraryPage";
import { MemoryPage } from "./pages/MemoryPage";
import { EvaluationPage, MissionDetailPage, MissionList, NewMission } from "./pages/pages";
import { draftFromHash } from "./components/workspaces";
import { parseRoute, type Route } from "./shell/routes";
import { INSIGHTS_TABS, LIBRARY_TABS, SectionTabs, Shell } from "./shell/Shell";

// The knowledge graph pages pull in three.js (~600 kB). Loaded only when opened (Phase 32).
const KnowledgeExplorer = lazy(() => import("./components/graph3d/KnowledgeExplorer"));
const AnalyzePage = lazy(() => import("./components/graph3d/AnalyzePage"));
const AttackGraphPage = lazy(() => import("./components/graph3d/AttackGraphPage"));

export default function App() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((hash: string) => {
    window.location.hash = hash;
  }, []);

  return (
    <Shell route={route}>
      {route.name === "home" ? <HomePage /> : null}
      {route.name === "cases" ? <CasesPage /> : null}
      {route.name === "case" ? <CasePage key={route.caseId} caseId={route.caseId} /> : null}

      {route.name === "list" ? (
        <MissionList onOpen={(runId) => go(`#/mission/${runId}`)} onNew={() => go("#/new")} />
      ) : null}

      {route.name === "new" ? (
        <NewMission
          key={route.key}
          draft={draftFromHash(route.key)}
          onStarted={(mission: MissionDetail) => go(`#/mission/${mission.run_id}`)}
          onCancel={() => go("#/")}
        />
      ) : null}

      {route.name === "mission" ? <JournalPage key={route.runId} runId={route.runId} /> : null}
      {route.name === "details" ? (
        <MissionDetailPage runId={route.runId} onBack={() => go(`#/mission/${route.runId}`)} />
      ) : null}

      {route.name === "knowledge" ? (
        <Suspense fallback={<div className="empty">Loading.</div>}>
          <AnalyzePage />
        </Suspense>
      ) : null}

      {route.name === "graph" ? (
        <>
          <div className="row" style={{ marginBottom: 20 }}>
            <button onClick={() => go(`#/mission/${route.runId}`)}>&larr; Investigation</button>
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

      {route.name === "attack" ? (
        <>
          <div className="row" style={{ marginBottom: 20 }}>
            <button onClick={() => go(`#/mission/${route.runId}`)}>&larr; Investigation</button>
          </div>
          <Suspense fallback={<div className="empty">Loading the 3D view.</div>}>
            <AttackGraphPage key={route.runId} runId={route.runId} />
          </Suspense>
        </>
      ) : null}

      {/* Library: evidence and documents, one place for every file (U3). */}
      {route.name === "evidence" || route.name === "documents" ? (
        <>
          <SectionTabs tabs={LIBRARY_TABS} active={route.name} />
          {route.name === "documents" ? (
            <DocumentsPage key={route.workspace} workspace={route.workspace} />
          ) : route.evidenceId ? (
            <EvidenceItemPage key={route.evidenceId} evidenceId={route.evidenceId} />
          ) : (
            <LibraryPage />
          )}
        </>
      ) : null}

      {/* Insights: quality, memory and recordings (U3). */}
      {route.name === "evaluation" || route.name === "benchmark" || route.name === "memory" || route.name === "replay" ? (
        <>
          <SectionTabs tabs={INSIGHTS_TABS} active={route.name} />
          {route.name === "evaluation" ? <EvaluationPage onBack={() => go("#/")} /> : null}
          {route.name === "benchmark" ? <BenchmarkPanel /> : null}
          {route.name === "memory" ? <MemoryPage key={route.entity} entity={route.entity} /> : null}
          {route.name === "replay" ? <RecordingsPage /> : null}
        </>
      ) : null}

      {route.name === "replayOne" ? <ReplayJournal key={route.file} file={route.file} /> : null}
      {route.name === "audit" ? <AuditPage /> : null}
      {route.name === "design" ? <DesignPage /> : null}
      {route.name === "settings" ? <SettingsPage /> : null}
    </Shell>
  );
}
