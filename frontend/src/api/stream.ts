/**
 * The conversation, streamed (v4 Phase 4): a POST whose response is server-sent events. EventSource
 * only GETs, so this reads the response body itself: `activity`, `words`, `verdict`, then `done`
 * with the thread, or `error`.
 */

import { ApiError, SIGNED_OUT } from "./client";
import type { Thread } from "./types";

export type TalkEvent =
  | { type: "activity"; text: string }
  | { type: "words"; claim: number; text: string }
  | { type: "verdict"; claim: number; status: string; citations: string[] }
  | { type: "done"; thread: Thread }
  | { type: "error"; message: string };

export interface TalkRequest {
  text?: string;
  regenerate?: string;
  edit?: string;
}

/** Complete events in `buffer`, and what is left over for the next chunk. */
export function parseEvents(buffer: string): { events: TalkEvent[]; rest: string } {
  const blocks = buffer.replaceAll("\r\n", "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: TalkEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");
    if (data) events.push(JSON.parse(data) as TalkEvent);
  }
  return { events, rest };
}

export async function streamTalk(caseId: string, body: TalkRequest, onEvent: (event: TalkEvent) => void): Promise<Thread> {
  const response = await fetch(`/api/v1/cases/${caseId}/conversation/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({ error_code: "UNREACHABLE", message: `the server returned ${response.status}`, run_id: null, details: {} }));
    if (response.status === 401) window.dispatchEvent(new Event(SIGNED_OUT));
    throw new ApiError(response.status, error);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseEvents(buffer + decoder.decode(value, { stream: true }));
    buffer = parsed.rest;
    for (const event of parsed.events) {
      onEvent(event);
      if (event.type === "done") return event.thread;
      if (event.type === "error") throw new ApiError(500, { error_code: "TALK_FAILED", message: event.message, run_id: null, details: {} });
    }
  }
  throw new ApiError(0, { error_code: "STREAM_ENDED", message: "The answer stopped before it finished.", run_id: null, details: {} });
}
