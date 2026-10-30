/**
 * The proof card (demo readiness): at the top of a finished investigation, what was checked and
 * how it stood up - the one panel that shows at a glance what an ordinary AI answer cannot.
 */

import type { ProofTally } from "./proof";

function Stat({ value, label, tone }: { value: string | number; label: string; tone?: string | undefined }) {
  return (
    <div className={`proof-stat${tone ? ` ${tone}` : ""}`}>
      <span className="proof-value">{value}</span>
      <span className="proof-label">{label}</span>
    </div>
  );
}

export function ProofCard({ tally }: { tally: ProofTally }) {
  return (
    <section className="proof-card" aria-label="How this answer was checked">
      <div className="proof-head">
        <strong>Every claim checked against the line it cites</strong>
        <span className="dim">by an independent verifier; dates and sums by code, not by the model</span>
      </div>
      <div className="proof-stats">
        <Stat value={tally.claims} label="claims checked" />
        <Stat value={tally.verified} label="verified" tone="good" />
        {tally.partly ? <Stat value={tally.partly} label="partly verified" tone="warn" /> : null}
        <Stat value={tally.caught} label="caught and rejected" tone={tally.caught ? "bad" : undefined} />
        {tally.unproven ? <Stat value={tally.unproven} label="not established" /> : null}
        <Stat value={tally.files} label="files fingerprinted (SHA-256)" />
        {tally.translated ? <Stat value={tally.translated} label="read in another language" /> : null}
        {tally.seconds !== null ? <Stat value={`${Math.floor(tally.seconds / 60)}m ${tally.seconds % 60}s`} label="end to end" /> : null}
      </div>
    </section>
  );
}
