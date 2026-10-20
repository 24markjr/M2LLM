/**
 * The static demo: the console with no engine behind it (the GitHub Pages build).
 *
 * Built with `VITE_STATIC_DEMO=1`. The committed recordings are published next to the page under
 * `demo/`, with `demo/index.json` naming them, so Recordings lists them and a replay plays in the
 * journal exactly as it does against the API. Everything else needs the engine and says so with
 * `STATIC_DEMO`, rather than pretending: a page that fails says why.
 */

import type { ApiErrorBody, Recording, RecordingSummary } from "./types";

export const STATIC_DEMO = import.meta.env.VITE_STATIC_DEMO === "1";

const DEMO_DIR = `${import.meta.env.BASE_URL}demo/`;
const BASE = "/api/v1";

export class DemoError extends Error {
  readonly body: ApiErrorBody;

  constructor(body: ApiErrorBody) {
    super(body.message);
    this.body = body;
  }
}

async function load<T>(file: string): Promise<T> {
  const response = await fetch(`${DEMO_DIR}${file}`);
  if (!response.ok) {
    throw new DemoError({
      error_code: "RECORDING_NOT_FOUND",
      message: `no recording named ${file}`,
      run_id: null,
      details: {},
    });
  }
  return (await response.json()) as T;
}

/** The same record the API builds in `app/api/recording.py::list_recordings`. */
function summarise(file: string, raw: Recording): RecordingSummary {
  const events = raw.events ?? [];
  const mission = raw.snapshot?.mission;
  return {
    run_id: raw.run_id,
    file,
    objective: raw.objective,
    model: raw.model,
    outcome: raw.outcome,
    recorded_at: raw.recorded_at,
    event_count: events.length,
    duration_ms: events.at(-1)?.t_offset_ms ?? 0,
    committed: true,
    findings: mission?.finding_count ?? 0,
    verified: mission?.verified_count ?? 0,
    case_id: mission?.case_id ?? "",
    hidden: "",
  };
}

export async function demoRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const route = path.split("?")[0] ?? path;

  if (route === "/health") {
    return { status: "static demo", model: "none (static demo)", provider_healthy: false } as T;
  }
  if (method === "GET" && route === `${BASE}/recordings`) {
    const files = await load<string[]>("index.json");
    const rows = await Promise.all(files.map(async (file) => summarise(file, await load<Recording>(file))));
    return rows.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at)) as T;
  }
  if (method === "GET" && route.startsWith(`${BASE}/recordings/`)) {
    return (await load<Recording>(decodeURIComponent(route.slice(`${BASE}/recordings/`.length)))) as T;
  }

  throw new DemoError({
    error_code: "STATIC_DEMO",
    message:
      "This is the static preview on GitHub Pages: there is no engine behind it. " +
      "Open Insights > Recordings to replay a real run, or run the full stack locally to investigate.",
    run_id: null,
    details: {},
  });
}
