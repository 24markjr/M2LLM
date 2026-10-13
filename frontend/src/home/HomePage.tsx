/**
 * Home (Phase U4): "What do you need to find out?" - the composer, the domain packs and their
 * starters, and what is waiting for you.
 */

import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { MissionSummary } from "../api/types";
import { browserStorage } from "../theme/theme";
import { Badge } from "../ui/components";
import { IconChevronRight } from "../ui/icons";
import { attentionItems } from "./attention";
import { Composer, type ComposerDraft } from "./Composer";
import { MODES } from "./modes";
import { PACK_KEY, packById, PACKS } from "./packs";

function loadPack(): string {
  try {
    return browserStorage()?.getItem(PACK_KEY) ?? "general";
  } catch {
    return "general";
  }
}

export function HomePage() {
  const [packId, setPackId] = useState(loadPack);
  const [draft, setDraft] = useState<ComposerDraft | null>(null);
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const pack = packById(packId);

  useEffect(() => {
    api.listMissions().then(setMissions).catch(() => setMissions([]));
  }, []);

  const choosePack = (id: string) => {
    setPackId(id);
    try {
      browserStorage()?.setItem(PACK_KEY, id);
    } catch {
      /* not remembered */
    }
  };

  const attention = attentionItems(missions, new Date());

  return (
    <div className="home">
      <section className="home-hero">
        <h1>What do you need to find out?</h1>
        <p>
          Ask a question and attach the files. JARVIS plans the work, reads every file, checks each finding against the
          lines it cites, and tells you what it could not establish.
        </p>
      </section>

      <div className="pack-picker" role="radiogroup" aria-label="Field">
        {PACKS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={p.id === pack.id}
            className={p.id === pack.id ? "on" : ""}
            title={p.blurb}
            onClick={() => choosePack(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <Composer pack={pack} draft={draft} />

      <section className="home-section" aria-labelledby="starters-title">
        <h2 id="starters-title">Try a question</h2>
        <div className="starters">
          {pack.starters.map((s) => (
            <button
              key={s.question}
              type="button"
              className="starter"
              onClick={() => setDraft({ question: s.question, files: s.files, mode: s.mode ?? pack.mode, key: Date.now() })}
            >
              <span className="starter-question">{s.question}</span>
              <span className="starter-meta">
                <Badge tone="accent">{MODES.find((m) => m.id === (s.mode ?? pack.mode))?.label}</Badge>
                {s.files.length ? `${s.files.length} example file(s)` : "attach your own files"}
              </span>
            </button>
          ))}
        </div>
      </section>

      {attention.length ? (
        <section className="home-section" aria-labelledby="attention-title">
          <h2 id="attention-title">Needs your attention</h2>
          <ul className="attention">
            {attention.map((item) => (
              <li key={item.key}>
                <a href={item.href} className={`attention-item ${item.kind}`}>
                  <span className="attention-dot" aria-hidden="true" />
                  <span className="attention-text">
                    <span className="attention-title">{item.title}</span>
                    <span className="attention-detail">{item.detail}</span>
                  </span>
                  <IconChevronRight size={16} />
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="home-links">
        <a href="#/knowledge">Quick analysis without an investigation</a>
        <span aria-hidden="true"> · </span>
        <a href="#/new">The detailed form</a>
        <span aria-hidden="true"> · </span>
        <a href="#/cases">All cases</a>
      </p>
    </div>
  );
}
