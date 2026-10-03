"""
memory/semantic_memory.py
Durable knowledge distilled from past investigations: subject-predicate-object
facts with provenance, independent of any single Q&A turn.
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import SemanticFact

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semantic_memory.db")


class SemanticMemory:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                fact_id TEXT PRIMARY KEY,
                subject TEXT, predicate TEXT, object TEXT,
                source TEXT, confidence REAL, created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_fact(self, subject: str, predicate: str, obj: str, source: str, confidence: float = 1.0) -> SemanticFact:
        fact = SemanticFact(subject=subject, predicate=predicate, object=obj, source=source, confidence=confidence)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO semantic_memory VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fact.fact_id, fact.subject, fact.predicate, fact.object, fact.source,
             fact.confidence, fact.created_at.isoformat()),
        )
        conn.commit()
        conn.close()
        return fact

    def query(self, subject: str = None, predicate: str = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        clauses, params = [], []
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if predicate:
            clauses.append("predicate = ?")
            params.append(predicate)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM semantic_memory {where}", params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def clear(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM semantic_memory")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    sm = SemanticMemory(db_path="/tmp/test_semantic_v2.db")
    sm.clear()
    sm.add_fact("Company ABC", "operates", "Mumbai Facility", source="report.pdf", confidence=0.9)
    sm.add_fact("Rahul Sharma", "works_for", "Company ABC", source="employee_statement.docx")
    print(sm.query(subject="Company ABC"))
