"""
memory/episodic_memory.py
Persistent log of every question/answer interaction, plus archived
investigation snapshots from WorkingMemory.
"""

import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import MemoryEntry, ClaimStatus

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "episodic_memory.db")


class EpisodicMemory:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                entry_id TEXT PRIMARY KEY,
                investigation_id TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_used TEXT,
                verification_status TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS investigations (
                investigation_id TEXT PRIMARY KEY,
                objective TEXT,
                snapshot_json TEXT,
                archived_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log(self, question: str, answer: str, sources_used: list[str] = None,
             verification_status: str = None, investigation_id: str = None) -> MemoryEntry:
        entry = MemoryEntry(
            investigation_id=investigation_id,
            question=question,
            answer=answer,
            sources_used=sources_used or [],
            verification_status=ClaimStatus(verification_status) if verification_status else None,
        )
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO episodic_memory VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry.entry_id, entry.investigation_id, entry.question, entry.answer,
             json.dumps(entry.sources_used),
             entry.verification_status.value if entry.verification_status else None,
             entry.created_at.isoformat()),
        )
        conn.commit()
        conn.close()
        return entry

    def archive_investigation(self, snapshot: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO investigations VALUES (?, ?, ?, ?)",
            (snapshot["investigation_id"], snapshot["objective"],
             json.dumps(snapshot), snapshot["started_at"]),
        )
        conn.commit()
        conn.close()

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM episodic_memory WHERE question LIKE ? OR answer LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def all_entries(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM episodic_memory ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def clear(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM episodic_memory")
        conn.execute("DELETE FROM investigations")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    mem = EpisodicMemory(db_path="/tmp/test_episodic_v2.db")
    mem.clear()
    mem.log("When did the incident occur?", "11:40 AM.", ["incident_report.pdf"], "SUPPORTED")
    mem.log("What was the employee's 2021 salary?", "Insufficient evidence.", [], "INSUFFICIENT_EVIDENCE")
    for e in mem.all_entries():
        print(f"[{e['verification_status']}] {e['question']} -> {e['answer']}")
