/**
 * The shell and its routing.
 *
 * Hash routing, deliberately: this app is served as static files next to an API, sometimes
 * from a file path, and a history-API router needs a server that rewrites unknown paths to
 * index.html. A hash works everywhere and a mission URL stays shareable.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import type { MissionDetail } from "./api/types";
import {
  EvaluationPage,
  MissionDetailPage,
  MissionList,
  NewMission,
  ReplayPage,
} from "./pages/pages";

type Route =
  | { name: "list" }
  | { name: "new" }
  | { name: "mission"; runId: string }
  | { name: "replay" }
  | { name: "evaluation" };

function parse(hash: string): Route {
  const match = /^#\/mission\/([\w-]+)$/.exec(hash);
  if (match?.[1]) return { name: "mission", runId: match[1] };
  if (hash === "#/new") return { name: "new" };
  if (hash === "#/replay") return { name: "replay" };
  if (hash === "#/evaluation") return { name: "evaluation" };
  return { name: "list" };
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
          <a className={route.name === "list" ? "on" : ""} href="#/">
            Missions
          </a>
          <a className={route.name === "replay" ? "on" : ""} href="#/replay">
            Replay
          </a>
          <a className={route.name === "evaluation" ? "on" : ""} href="#/evaluation">
            Evaluation
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

      {route.name === "list" ? (
        <MissionList
          onOpen={(runId) => go(`#/mission/${runId}`)}
          onNew={() => go("#/new")}
        />
      ) : null}

      {route.name === "new" ? (
        <NewMission
          onStarted={(mission: MissionDetail) => go(`#/mission/${mission.run_id}`)}
          onCancel={() => go("#/")}
        />
      ) : null}

      {route.name === "mission" ? (
        <MissionDetailPage runId={route.runId} onBack={() => go("#/")} />
      ) : null}

      {route.name === "replay" ? <ReplayPage onBack={() => go("#/")} /> : null}

      {route.name === "evaluation" ? <EvaluationPage onBack={() => go("#/")} /> : null}
    </div>
  );
}
