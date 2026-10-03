import sqlite3
import uuid

DB_PATH = "jarvis_knowledge.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS entities (
        entity_id TEXT PRIMARY KEY, type TEXT, name TEXT,
        source_document TEXT, source_page INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS entity_sources (
        entity_id TEXT, source_document TEXT, source_page INTEGER,
        UNIQUE(entity_id, source_document, source_page))""")
    c.execute("""CREATE TABLE IF NOT EXISTS relationships (
        relationship_id TEXT PRIMARY KEY, subject TEXT, predicate TEXT,
        object TEXT, source_document TEXT, source_page INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS claims (
        claim_id TEXT PRIMARY KEY, entity TEXT, attribute TEXT, value TEXT,
        source_document TEXT, source_page INTEGER)""")
    conn.commit()
    conn.close()

def find_or_create_entity(name: str, type_: str, source_document: str, source_page=None):
    """Entity resolution: same name (case-insensitive) = same entity_id, across all documents."""
    normalized = name.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT entity_id FROM entities WHERE LOWER(name)=?", (normalized,)).fetchone()
    if row:
        entity_id = row["entity_id"]
    else:
        entity_id = f"ENT-{uuid.uuid4().hex[:8]}"
        conn.execute("INSERT INTO entities VALUES (?,?,?,?,?)",
            (entity_id, type_, name, source_document, source_page))
    conn.execute("INSERT OR IGNORE INTO entity_sources VALUES (?,?,?)",
        (entity_id, source_document, source_page))
    conn.commit()
    conn.close()
    return entity_id

def insert_relationship(r: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO relationships VALUES (?,?,?,?,?,?)",
        (r["relationship_id"], r["subject"], r["predicate"], r["object"],
         r["source_document"], r.get("source_page")))
    conn.commit(); conn.close()

def insert_claim(c: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?,?)",
        (c["claim_id"], c["entity"], c["attribute"], c["value"],
         c["source_document"], c.get("source_page")))
    conn.commit(); conn.close()

def get_all(table: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def find_entity_by_name(name: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM entities WHERE name LIKE ?", (f"%{name}%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sources_for_entity(entity_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM entity_sources WHERE entity_id=?", (entity_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_relationships_for_entity(entity_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM relationships WHERE subject=? OR object=?",
        (entity_id, entity_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_claim(claim_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    conn.close()
    return dict(row) if row else None