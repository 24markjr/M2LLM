/**
 * Where Member 3's views get their data (Phase 36): one interface, two sources.
 *
 * A mission's knowledge base is stored, so every view asks the API (`/knowledge/search`,
 * `/timeline`, `/conflicts`, `/investigation`, `/timeline/compare`). An analysis (`#/knowledge`) is
 * not stored, but its response carries the whole knowledge base and its timeline, so the views are
 * built in the browser from that - except search and date comparison, which run Member 3's scoring
 * and the temporal comparison on the server and need a stored base. `stored` says which, so a panel
 * can explain itself instead of failing.
 */

import { ApiError, api } from "../../api/client";
import type {
  ClaimComparison,
  ClaimConflict,
  EntityInvestigation,
  KnowledgeSnapshot,
  SearchHit,
  TimelineEvent,
} from "../../api/types";
import { forEntity, localInvestigation } from "./investigation";

export interface KnowledgeAccess {
  /** Search and comparison are available. */
  readonly stored: boolean;
  search(query: string, depth: number): Promise<SearchHit[]>;
  timeline(entityId?: string): Promise<TimelineEvent[]>;
  conflicts(entityId?: string): Promise<ClaimConflict[]>;
  /** Null when no entity has that name. */
  investigate(name: string): Promise<EntityInvestigation | null>;
  compare(claimA: string, claimB: string): Promise<ClaimComparison | null>;
}

export function missionAccess(runId: string): KnowledgeAccess {
  return {
    stored: true,
    search: (query, depth) => api.searchKnowledge(runId, query, depth),
    timeline: (entityId) => api.getTimeline(runId, entityId),
    conflicts: (entityId) => api.getConflicts(runId, entityId),
    investigate: async (name) => {
      try {
        return await api.investigate(runId, name);
      } catch (exc: unknown) {
        if (exc instanceof ApiError && exc.code === "ENTITY_NOT_FOUND") return null;
        throw exc;
      }
    },
    compare: (claimA, claimB) => api.compareClaims(runId, claimA, claimB),
  };
}

export function analysisAccess(snapshot: KnowledgeSnapshot, timeline: TimelineEvent[]): KnowledgeAccess {
  return {
    stored: false,
    search: () => Promise.resolve([]),
    timeline: (entityId) => Promise.resolve(forEntity(timeline, entityId ?? null)),
    conflicts: (entityId) => Promise.resolve(forEntity(snapshot.conflicts, entityId ?? null)),
    investigate: (name) => Promise.resolve(localInvestigation(snapshot, name)),
    compare: () => Promise.resolve(null),
  };
}
