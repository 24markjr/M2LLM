/** The running investigation's progress line, ticking every second (see `progress.ts`). */

import { useEffect, useState } from "react";

import type { EventRecord } from "../api/types";
import { progressLine, progressOf } from "./progress";

export function ProgressLine({
  events,
  startedAt,
  tasksTotal,
}: {
  events: EventRecord[];
  startedAt: string;
  tasksTotal: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);
  const elapsed = (now - new Date(startedAt).getTime()) / 1000;
  return (
    <div className="progress-line" role="status" aria-live="polite">
      <span className="progress-pulse" aria-hidden="true" />
      {progressLine(progressOf(events, tasksTotal), elapsed)}
    </div>
  );
}
