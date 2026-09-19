from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects (
  project_key TEXT PRIMARY KEY,
  root TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  project_key TEXT NOT NULL,
  host TEXT NOT NULL,
  cwd TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  ended_at INTEGER,
  metadata TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(project_key) REFERENCES projects(project_key)
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_key TEXT NOT NULL,
  topic_key TEXT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_session TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(project_key, topic_key)
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  title, content, topic_key, kind,
  content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid,title,content,topic_key,kind)
  VALUES (new.id,new.title,new.content,coalesce(new.topic_key,''),new.kind);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts,rowid,title,content,topic_key,kind)
  VALUES('delete',old.id,old.title,old.content,coalesce(old.topic_key,''),old.kind);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts,rowid,title,content,topic_key,kind)
  VALUES('delete',old.id,old.title,old.content,coalesce(old.topic_key,''),old.kind);
  INSERT INTO memories_fts(rowid,title,content,topic_key,kind)
  VALUES (new.id,new.title,new.content,coalesce(new.topic_key,''),new.kind);
END;
CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_key TEXT NOT NULL,
  session_id TEXT,
  created_at INTEGER NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  project_key TEXT NOT NULL,
  path TEXT NOT NULL,
  lang TEXT,
  digest TEXT NOT NULL,
  mtime_ns INTEGER NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(project_key,path)
);
CREATE TABLE IF NOT EXISTS symbols (
  project_key TEXT NOT NULL,
  path TEXT NOT NULL,
  symbol TEXT NOT NULL,
  kind TEXT NOT NULL,
  line INTEGER NOT NULL,
  PRIMARY KEY(project_key,path,symbol,kind,line)
);
CREATE TABLE IF NOT EXISTS edges (
  project_key TEXT NOT NULL,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  kind TEXT NOT NULL,
  evidence TEXT NOT NULL,
  PRIMARY KEY(project_key,src,dst,kind,evidence)
);
CREATE INDEX IF NOT EXISTS idx_memories_project_updated ON memories(project_key,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_handoffs_project_created ON handoffs(project_key,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_symbols_project_symbol ON symbols(project_key,symbol);
CREATE INDEX IF NOT EXISTS idx_edges_project_src ON edges(project_key,src);
"""

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @classmethod
    def default(cls) -> "Store":
        return cls(Path.home() / ".continuity" / "continuity.db")

    def close(self) -> None:
        self.db.close()

    def ensure_project(self, key: str, root: str) -> None:
        now = int(time.time())
        self.db.execute(
            "INSERT INTO projects(project_key,root,created_at,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(project_key) DO UPDATE SET root=excluded.root,updated_at=excluded.updated_at",
            (key, root, now, now),
        )
        self.db.commit()

    def start_session(self, sid: str, project_key: str, host: str, cwd: str, metadata: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO sessions(id,project_key,host,cwd,started_at,metadata) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata",
            (sid, project_key, host, cwd, int(time.time()), json.dumps(metadata or {}, sort_keys=True)),
        )
        self.db.commit()

    def end_session(self, sid: str) -> None:
        self.db.execute("UPDATE sessions SET ended_at=? WHERE id=?", (int(time.time()), sid))
        self.db.commit()

    def save_memory(self, project_key: str, title: str, content: str, kind: str = "discovery", topic_key: str | None = None, session_id: str | None = None, pinned: bool = False) -> int:
        now = int(time.time())
        if topic_key:
            self.db.execute(
                "INSERT INTO memories(project_key,topic_key,kind,title,content,source_session,pinned,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(project_key,topic_key) DO UPDATE SET "
                "kind=excluded.kind,title=excluded.title,content=excluded.content,source_session=excluded.source_session,pinned=excluded.pinned,updated_at=excluded.updated_at",
                (project_key, topic_key, kind, title, content, session_id, int(pinned), now, now),
            )
            row = self.db.execute("SELECT id FROM memories WHERE project_key=? AND topic_key=?", (project_key, topic_key)).fetchone()
        else:
            cur = self.db.execute(
                "INSERT INTO memories(project_key,topic_key,kind,title,content,source_session,pinned,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (project_key, None, kind, title, content, session_id, int(pinned), now, now),
            )
            row = {"id": cur.lastrowid}
        self.db.commit()
        return int(row["id"])

    def search_memory(self, project_key: str, query: str, limit: int = 8) -> list[sqlite3.Row]:
        q = query.strip()
        if not q:
            return list(self.db.execute("SELECT * FROM memories WHERE project_key=? ORDER BY pinned DESC,updated_at DESC LIMIT ?", (project_key, limit)))
        try:
            return list(self.db.execute(
                "SELECT m.*, bm25(memories_fts) score FROM memories_fts JOIN memories m ON m.id=memories_fts.rowid "
                "WHERE m.project_key=? AND memories_fts MATCH ? ORDER BY m.pinned DESC,score LIMIT ?",
                (project_key, q, limit),
            ))
        except sqlite3.OperationalError:
            like = f"%{q}%"
            return list(self.db.execute(
                "SELECT * FROM memories WHERE project_key=? AND (title LIKE ? OR content LIKE ? OR topic_key LIKE ?) ORDER BY pinned DESC,updated_at DESC LIMIT ?",
                (project_key, like, like, like, limit),
            ))

    def add_handoff(self, project_key: str, session_id: str | None, payload: dict) -> int:
        cur = self.db.execute("INSERT INTO handoffs(project_key,session_id,created_at,payload) VALUES(?,?,?,?)", (project_key, session_id, int(time.time()), json.dumps(payload, sort_keys=True)))
        self.db.commit()
        return int(cur.lastrowid)

    def latest_handoff(self, project_key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM handoffs WHERE project_key=? ORDER BY created_at DESC LIMIT 1", (project_key,)).fetchone()
        if not row:
            return None
        p = json.loads(row["payload"])
        p["_id"] = row["id"]
        p["_created_at"] = row["created_at"]
        return p

    def replace_index(self, project_key: str, files: Iterable[dict], symbols: Iterable[dict], edges: Iterable[dict]) -> None:
        with self.db:
            self.db.execute("DELETE FROM files WHERE project_key=?", (project_key,))
            self.db.execute("DELETE FROM symbols WHERE project_key=?", (project_key,))
            self.db.execute("DELETE FROM edges WHERE project_key=?", (project_key,))
            self.db.executemany("INSERT INTO files(project_key,path,lang,digest,mtime_ns,summary) VALUES(?,?,?,?,?,?)", [(project_key, x['path'], x.get('lang'), x['digest'], x['mtime_ns'], x.get('summary','')) for x in files])
            self.db.executemany("INSERT INTO symbols(project_key,path,symbol,kind,line) VALUES(?,?,?,?,?)", [(project_key, x['path'], x['symbol'], x['kind'], x['line']) for x in symbols])
            self.db.executemany("INSERT INTO edges(project_key,src,dst,kind,evidence) VALUES(?,?,?,?,?)", [(project_key, x['src'], x['dst'], x['kind'], x['evidence']) for x in edges])

    def search_symbols(self, project_key: str, term: str, limit: int = 15) -> list[sqlite3.Row]:
        like = f"%{term}%"
        return list(self.db.execute("SELECT * FROM symbols WHERE project_key=? AND (symbol LIKE ? OR path LIKE ?) ORDER BY path,line LIMIT ?", (project_key, like, like, limit)))

    def neighbors(self, project_key: str, node: str, limit: int = 30) -> list[sqlite3.Row]:
        like = f"%{node}%"
        return list(self.db.execute("SELECT * FROM edges WHERE project_key=? AND (src LIKE ? OR dst LIKE ?) LIMIT ?", (project_key, like, like, limit)))
