/**
 * The first-run tour (Phase U11): four steps on the home page, shown until the person dismisses it,
 * and reopened from the shortcuts dialog. A convenience kept in this browser only.
 */

import { useState } from "react";

import { browserStorage } from "../theme/theme";

export const TOUR_KEY = "jarvis.tour";

const STEPS = [
  { title: "Ask, and attach the files", body: "Type what you need to find out and drop in the documents, logs, scans or recordings. Or start from a question below." },
  { title: "Watch it work", body: "The journal shows the plan in plain steps. Each finding cites a file and a line, and is checked by a verifier that never saw the reasoning." },
  { title: "Check the receipts", body: "Click a citation to see the cited line highlighted on the evidence board. The pin board joins findings that share evidence; Proof compares the answer with the plain model." },
  { title: "Everything is kept and accountable", body: "The Library holds every file with its chain of custody. Activity is the audit log. Nothing leaves this computer." },
];

function seen(): boolean {
  try {
    return browserStorage()?.getItem(TOUR_KEY) === "done";
  } catch {
    return false;
  }
}

export function reopenTour(): void {
  try {
    browserStorage()?.setItem(TOUR_KEY, "");
  } catch {
    // Not remembered; the tour simply shows.
  }
}

export function Tour() {
  const [open, setOpen] = useState(() => !seen());
  const [step, setStep] = useState(0);
  if (!open) return null;

  const close = () => {
    setOpen(false);
    try {
      browserStorage()?.setItem(TOUR_KEY, "done");
    } catch {
      // Shown again next time; harmless.
    }
  };
  const current = STEPS[step] ?? STEPS[0]!;
  const last = step === STEPS.length - 1;

  return (
    <section className="tour" aria-labelledby="tour-title">
      <div className="tour-head">
        <span className="tour-step">
          Welcome · {step + 1} of {STEPS.length}
        </span>
        <button type="button" className="ui-button ghost sm" onClick={close}>
          Skip
        </button>
      </div>
      <h2 id="tour-title">{current.title}</h2>
      <p>{current.body}</p>
      <div className="tour-actions">
        <div className="tour-dots" aria-hidden="true">
          {STEPS.map((_, i) => (
            <span key={i} className={i === step ? "on" : ""} />
          ))}
        </div>
        {step > 0 ? (
          <button type="button" className="ui-button ghost sm" onClick={() => setStep(step - 1)}>
            Back
          </button>
        ) : null}
        <button type="button" className="ui-button primary sm" onClick={last ? close : () => setStep(step + 1)}>
          {last ? "Start" : "Next"}
        </button>
      </div>
    </section>
  );
}
