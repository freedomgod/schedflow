"""Actor scoped SQLite assistant history, receipts and recoverable event journal."""

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from schedflow.configs import config


def timestamp():
    return datetime.now(UTC).isoformat()


def uid():
    return uuid.uuid4().hex


class AgentRepository:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory
        self.lock = threading.RLock()

    @contextmanager
    def connect(self):
        # Constructing an application is read-only; migrate on the first actual use.
        # Resolve config._get_conn at call time so isolated test databases stay isolated.
        conn = (self.connection_factory or config._get_conn)()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO agent_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS agent_records(
                    kind TEXT NOT NULL, id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                    session_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS agent_actor_session
                    ON agent_records(actor,session_id,kind);
                CREATE TABLE IF NOT EXISTS agent_events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
                    session_id TEXT NOT NULL, turn_id TEXT, type TEXT NOT NULL,payload TEXT NOT NULL);
            """)
            with conn:
                yield conn
        finally:
            conn.close()

    def put(self, kind, actor, session_id, data):
        if kind == "message":
            from .schemas import AgentMessage

            AgentMessage.model_validate(data)
        key = data[kind + "_id"]
        with self.lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO agent_records VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (
                    kind,
                    key,
                    actor,
                    session_id,
                    json.dumps(data, ensure_ascii=False, default=str),
                ),
            )
            if kind in {"turn", "message", "proposal"}:
                row = conn.execute(
                    "SELECT data FROM agent_records WHERE kind='session' AND actor=? AND id=?",
                    (actor, session_id),
                ).fetchone()
                if row:
                    session = json.loads(row[0])
                    session["updated_at"] = timestamp()
                    conn.execute(
                        "UPDATE agent_records SET data=? WHERE id=?",
                        (json.dumps(session), session_id),
                    )
        return data

    def get(self, kind, actor, key):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT data FROM agent_records WHERE kind=? AND actor=? AND id=?",
                (kind, actor, key),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind, actor, session_id=None):
        sql = "SELECT data FROM agent_records WHERE kind=? AND actor=?"
        args = [kind, actor]
        if session_id is not None:
            sql += " AND session_id=?"
            args.append(session_id)
        with self.connect() as conn:
            rows = conn.execute(sql + " ORDER BY rowid", args).fetchall()
        return [json.loads(row[0]) for row in rows]

    def create_session(self, actor, title=None):
        now = timestamp()
        data = {
            "session_id": uid(),
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
        }
        return self.put("session", actor, data["session_id"], data)

    def get_session(self, actor, key):
        with self.lock:
            data = self.get("session", actor, key)
            if data:
                data = {
                    **data,
                    "messages": self.list("message", actor, key),
                    "turns": self.list("turn", actor, key),
                    "proposals": self.list("proposal", actor, key),
                    "last_seq": self.last_seq(actor, key),
                }
        return data

    def last_seq(self, actor, session_id):
        with self.connect() as conn:
            return conn.execute(
                "SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE actor=? AND session_id=?",
                (actor, session_id),
            ).fetchone()[0]

    def delete_session(self, actor, key):
        with self.lock, self.connect() as conn:
            conn.execute(
                "DELETE FROM agent_events WHERE actor=? AND session_id=?", (actor, key)
            )
            # Receipts and their immutable identity survive removal of conversational content.
            rows = conn.execute(
                "SELECT id,kind,data FROM agent_records WHERE actor=? AND session_id=? "
                "AND kind IN ('operation','proposal')",
                (actor, key),
            ).fetchall()
            for record_id, kind, encoded in rows:
                data = json.loads(encoded)
                if kind == "proposal":
                    retained = {
                        k: data.get(k)
                        for k in (
                            "proposal_id",
                            "version",
                            "status",
                            "action",
                            "job_id",
                            "session_id",
                            "operation_id",
                            "expires_at",
                            "target_hash",
                        )
                    }
                    if not retained["operation_id"]:
                        retained["status"] = "rejected"
                else:
                    retained = {**data, "result": None, "error": None}
                conn.execute(
                    "UPDATE agent_records SET data=? WHERE id=?",
                    (json.dumps(retained), record_id),
                )
            conn.execute(
                "DELETE FROM agent_records WHERE actor=? AND session_id=? AND kind NOT IN ('operation','proposal')",
                (actor, key),
            )

    def add_event(self, actor, session_id, turn_id, kind, payload):
        with self.lock, self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO agent_events(actor,session_id,turn_id,type,payload) "
                "VALUES(?,?,?,?,?)",
                (
                    actor,
                    session_id,
                    turn_id,
                    kind,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            return cursor.lastrowid

    def finalize_turn(
        self, actor, session_id, turn, message, terminal_kind, terminal_payload
    ):
        """Commit the terminal snapshot and its cursor together, including crash recovery."""
        from .schemas import AgentMessage

        AgentMessage.model_validate(message)
        with self.lock, self.connect() as conn:
            for kind, data in (("turn", turn), ("message", message)):
                conn.execute(
                    "INSERT INTO agent_records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (
                        kind,
                        data[kind + "_id"],
                        actor,
                        session_id,
                        json.dumps(data, ensure_ascii=False),
                    ),
                )
            for kind, payload in (
                ("message.completed", {"message": message}),
                (terminal_kind, terminal_payload),
            ):
                conn.execute(
                    "INSERT INTO agent_events(actor,session_id,turn_id,type,payload) VALUES(?,?,?,?,?)",
                    (
                        actor,
                        session_id,
                        turn["turn_id"],
                        kind,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )

    def events(self, actor, session_id, after):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT seq,turn_id,type,payload FROM agent_events "
                "WHERE actor=? AND session_id=? AND seq>? ORDER BY seq LIMIT 500",
                (actor, session_id, after),
            ).fetchall()
        return [
            {"seq": r[0], "turn_id": r[1], "type": r[2], "payload": json.loads(r[3])}
            for r in rows
        ]

    def recover(self):
        """Do not retry a potentially committed scheduler mutation after a crash."""
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                "SELECT id,kind,data,actor,session_id FROM agent_records WHERE kind IN ('turn','operation')"
            ).fetchall()
            for key, kind, encoded, actor, session_id in rows:
                data = json.loads(encoded)
                active = (
                    {"queued", "running"}
                    if kind == "turn"
                    else {"prepared", "committing", "accepted", "running"}
                )
                if data.get("status") in active:
                    data["status"] = "interrupted" if kind == "turn" else "unknown"
                    conn.execute(
                        "UPDATE agent_records SET data=? WHERE id=?",
                        (json.dumps(data), key),
                    )
                    if kind == "turn":
                        messages = conn.execute(
                            "SELECT id,data FROM agent_records WHERE kind='message' AND actor=? AND session_id=?",
                            (actor, session_id),
                        ).fetchall()
                        for message_id, message_encoded in messages:
                            message = json.loads(message_encoded)
                            if (
                                message.get("turn_id") == key
                                and message["status"] == "streaming"
                            ):
                                message["status"] = "interrupted"
                                message["blocks"].append(
                                    {
                                        "type": "error",
                                        "message": "Agent turn interrupted by server restart",
                                    }
                                )
                                conn.execute(
                                    "UPDATE agent_records SET data=? WHERE id=?",
                                    (json.dumps(message), message_id),
                                )
                                conn.execute(
                                    "INSERT INTO agent_events(actor,session_id,turn_id,type,payload) VALUES(?,?,?,?,?)",
                                    (
                                        actor,
                                        session_id,
                                        key,
                                        "message.completed",
                                        json.dumps({"message": message}),
                                    ),
                                )
                        conn.execute(
                            "INSERT INTO agent_events(actor,session_id,turn_id,type,payload) VALUES(?,?,?,?,?)",
                            (
                                actor,
                                session_id,
                                key,
                                "turn.failed",
                                json.dumps(
                                    {
                                        "status": "interrupted",
                                        "message": "Agent turn interrupted by server restart",
                                    }
                                ),
                            ),
                        )

    def cleanup(self, retention_days=30):
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        with self.lock:
            with self.connect() as conn:
                rows = conn.execute(
                    "SELECT actor,id,data FROM agent_records WHERE kind='session'"
                ).fetchall()
            for actor, key, encoded in rows:
                session = json.loads(encoded)
                last_used = datetime.fromisoformat(
                    session.get("updated_at") or session["created_at"]
                )
                if last_used >= cutoff:
                    continue
                if any(
                    t["status"] in {"queued", "running"}
                    for t in self.list("turn", actor, key)
                ):
                    continue
                if any(
                    o["status"] in {"prepared", "committing", "accepted", "running"}
                    for o in self.list("operation", actor, key)
                ):
                    continue
                self.delete_session(actor, key)
