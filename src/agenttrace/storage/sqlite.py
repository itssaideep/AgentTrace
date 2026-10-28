"""SQLite analytical store ingesting JSONL trace streams for relational analysis."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agenttrace.schemas import RecordType


class SQLiteTraceStore:
    """Relational SQLite storage engine for AgentTrace records."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and analytical indices."""
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY,
                parent_span_id TEXT,
                task_id TEXT,
                agent_id TEXT,
                name TEXT,
                kind TEXT,
                status TEXT,
                start_monotonic_ns INTEGER,
                end_monotonic_ns INTEGER,
                duration_ns INTEGER,
                duration_ms REAL,
                error_message TEXT,
                attributes_json TEXT
            );

            CREATE TABLE IF NOT EXISTS span_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                span_id TEXT NOT NULL,
                name TEXT NOT NULL,
                timestamp_monotonic_ns INTEGER NOT NULL,
                attributes_json TEXT
            );

            CREATE TABLE IF NOT EXISTS span_dependencies (
                span_id TEXT NOT NULL,
                depends_on_span_id TEXT NOT NULL,
                PRIMARY KEY (span_id, depends_on_span_id)
            );

            CREATE TABLE IF NOT EXISTS resource_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_monotonic_ns INTEGER NOT NULL,
                process_id INTEGER NOT NULL,
                cpu_user_s REAL,
                cpu_sys_s REAL,
                rss_bytes INTEGER,
                num_threads INTEGER,
                voluntary_ctx_switches INTEGER,
                involuntary_ctx_switches INTEGER,
                read_bytes INTEGER,
                write_bytes INTEGER
            );

            CREATE TABLE IF NOT EXISTS system_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_monotonic_ns INTEGER NOT NULL,
                cpu_percent REAL,
                memory_total_bytes INTEGER,
                memory_available_bytes INTEGER,
                disk_read_bytes INTEGER,
                disk_write_bytes INTEGER,
                net_sent_bytes INTEGER,
                net_recv_bytes INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_spans_task ON spans(task_id);
            CREATE INDEX IF NOT EXISTS idx_spans_time
                ON spans(start_monotonic_ns, end_monotonic_ns);
            CREATE INDEX IF NOT EXISTS idx_res_time ON resource_samples(timestamp_monotonic_ns);
            CREATE INDEX IF NOT EXISTS idx_sys_time ON system_samples(timestamp_monotonic_ns);
        """)
        self.conn.commit()

    def ingest_jsonl(self, jsonl_path: str | Path) -> int:
        """Read a JSONL file and populate database tables.

        Returns total records ingested.
        """
        path = Path(jsonl_path)
        if not path.is_file():
            raise FileNotFoundError(f"Trace file not found: {path}")

        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    records.append(json.loads(line_str))

        return self.ingest_records(records)

    def ingest_records(self, records: list[dict[str, Any]]) -> int:
        """Ingest a list of dictionary records into SQLite."""
        cursor = self.conn.cursor()

        starts: dict[str, dict[str, Any]] = {}
        ends: dict[str, dict[str, Any]] = {}
        events: list[dict[str, Any]] = []
        resource_samples: list[dict[str, Any]] = []

        for r in records:
            rtype = r.get("record_type")
            if rtype == RecordType.SPAN_START.value:
                starts[r["span_id"]] = r
            elif rtype == RecordType.SPAN_END.value:
                ends[r["span_id"]] = r
            elif rtype == RecordType.SPAN_EVENT.value:
                events.append(r)
            elif rtype == RecordType.RESOURCE_SAMPLE.value:
                resource_samples.append(r)

        # Ingest spans (pair starts and ends)
        all_span_ids = set(starts.keys()) | set(ends.keys())
        for sid in all_span_ids:
            s_rec = starts.get(sid, {})
            e_rec = ends.get(sid, {})

            parent_id = s_rec.get("parent_span_id")
            task_id = s_rec.get("task_id")
            agent_id = s_rec.get("agent_id")
            name = s_rec.get("name") or e_rec.get("name", "")
            kind = s_rec.get("kind", "internal")
            status = e_rec.get("status", "incomplete" if sid not in ends else "ok")
            start_ns = s_rec.get("timestamp_monotonic_ns")
            end_ns = e_rec.get("timestamp_monotonic_ns")
            duration_ns = (
                (end_ns - start_ns) if (start_ns is not None and end_ns is not None) else None
            )
            duration_ms = (duration_ns / 1_000_000.0) if duration_ns is not None else None
            err_msg = e_rec.get("error_message")

            attrs = {**s_rec.get("attributes", {}), **e_rec.get("attributes", {})}
            attrs_json = json.dumps(attrs)

            cursor.execute(
                """
                INSERT OR REPLACE INTO spans (
                    span_id, parent_span_id, task_id, agent_id, name, kind,
                    status, start_monotonic_ns, end_monotonic_ns, duration_ns,
                    duration_ms, error_message, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    parent_id,
                    task_id,
                    agent_id,
                    name,
                    kind,
                    status,
                    start_ns,
                    end_ns,
                    duration_ns,
                    duration_ms,
                    err_msg,
                    attrs_json,
                ),
            )

            # Dependencies
            deps = attrs.get("depends_on", [])
            if isinstance(deps, list):
                for dep in deps:
                    cursor.execute(
                        "INSERT OR IGNORE INTO span_dependencies VALUES (?, ?)",
                        (sid, str(dep)),
                    )

        # Ingest events
        for ev in events:
            ev_attrs = json.dumps(ev.get("attributes", {}))
            cursor.execute(
                """
                INSERT INTO span_events (span_id, name, timestamp_monotonic_ns, attributes_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    ev.get("span_id", ""),
                    ev.get("name", ""),
                    ev.get("timestamp_monotonic_ns", 0),
                    ev_attrs,
                ),
            )

        # Ingest resource and system samples
        for sm in resource_samples:
            ts = sm.get("timestamp_monotonic_ns", 0)
            for pm in sm.get("process_metrics", []):
                cursor.execute(
                    """
                    INSERT INTO resource_samples (
                        timestamp_monotonic_ns, process_id, cpu_user_s, cpu_sys_s,
                        rss_bytes, num_threads, voluntary_ctx_switches,
                        involuntary_ctx_switches, read_bytes, write_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        pm.get("process_id", 0),
                        pm.get("cpu_user_time_s"),
                        pm.get("cpu_system_time_s"),
                        pm.get("rss_bytes"),
                        pm.get("num_threads"),
                        pm.get("voluntary_context_switches"),
                        pm.get("involuntary_context_switches"),
                        pm.get("disk_read_bytes"),
                        pm.get("disk_write_bytes"),
                    ),
                )

            sys = sm.get("system_metrics")
            if sys:
                cursor.execute(
                    """
                    INSERT INTO system_samples (
                        timestamp_monotonic_ns, cpu_percent, memory_total_bytes,
                        memory_available_bytes, disk_read_bytes, disk_write_bytes,
                        net_sent_bytes, net_recv_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        sys.get("system_cpu_percent"),
                        sys.get("system_memory_total_bytes"),
                        sys.get("system_memory_available_bytes"),
                        sys.get("system_disk_read_bytes"),
                        sys.get("system_disk_write_bytes"),
                        sys.get("system_net_bytes_sent"),
                        sys.get("system_net_bytes_recv"),
                    ),
                )

        self.conn.commit()
        return len(records)

    def get_spans(self) -> list[dict[str, Any]]:
        """Retrieve all spans as dictionary rows."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM spans ORDER BY start_monotonic_ns ASC")
        return [dict(row) for row in cursor.fetchall()]

    def get_resource_samples(
        self, start_ns: int | None = None, end_ns: int | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve resource samples, optionally bounded by monotonic time."""
        cursor = self.conn.cursor()
        if start_ns is not None and end_ns is not None:
            cursor.execute(
                """
                SELECT * FROM resource_samples
                WHERE timestamp_monotonic_ns BETWEEN ? AND ?
                ORDER BY timestamp_monotonic_ns ASC
                """,
                (start_ns, end_ns),
            )
        else:
            cursor.execute("SELECT * FROM resource_samples ORDER BY timestamp_monotonic_ns ASC")
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close SQLite database connection."""
        self.conn.close()

    def __enter__(self) -> SQLiteTraceStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
