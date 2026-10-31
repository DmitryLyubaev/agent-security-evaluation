import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .domain import Evidence, ExceptionRecord, canonical


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS records(
                run_id TEXT, id TEXT, account TEXT, status TEXT, version INTEGER, evidence TEXT,
                PRIMARY KEY(run_id,id));
            CREATE TABLE IF NOT EXISTS proposals(
                id TEXT PRIMARY KEY, data TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(
                proposal_id TEXT PRIMARY KEY REFERENCES proposals(id), digest TEXT NOT NULL,
                approver TEXT, account TEXT, approved INTEGER NOT NULL, consumed INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, run_id TEXT, name TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS studies(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS labels(id TEXT PRIMARY KEY, study_id TEXT, data TEXT NOT NULL);
        """)

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def seed_records(self, run_id, records):
        with self.transaction():
            for record in records:
                self.conn.execute(
                    "INSERT INTO records VALUES(?,?,?,?,?,?)",
                    (
                        run_id,
                        record.exception_id,
                        record.account_id,
                        record.status,
                        record.version,
                        canonical([asdict(e) for e in record.evidence]),
                    ),
                )

    def get_record(self, run_id, exception_id):
        row = self.conn.execute(
            "SELECT * FROM records WHERE run_id=? AND id=?", (run_id, exception_id)
        ).fetchone()
        if not row:
            return None
        return ExceptionRecord(
            row["id"],
            row["account"],
            row["status"],
            row["version"],
            tuple(Evidence(**e) for e in json.loads(row["evidence"])),
        )

    def get_proposal(self, proposal_id):
        row = self.conn.execute("SELECT data FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def audit(self, context, call, result):
        data = {
            "actor_id": context.actor_id,
            "account_id": context.account_id,
            "call": asdict(call),
            "result": result.to_dict(),
        }
        self.conn.execute(
            "INSERT INTO events(run_id,name,data) VALUES(?,?,?)",
            (context.run_id, call.name, canonical(data)),
        )

    def events(self, run_id):
        return [
            json.loads(r[0])
            for r in self.conn.execute(
                "SELECT data FROM events WHERE run_id=? ORDER BY id", (run_id,)
            )
        ]

    def save_run_data(self, data):
        self.conn.execute(
            "INSERT INTO runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (data["run_id"], canonical(data)),
        )

    def run_data(self, run_id):
        row = self.conn.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError("unknown_run")
        return json.loads(row[0])

    def close(self):
        self.conn.close()
