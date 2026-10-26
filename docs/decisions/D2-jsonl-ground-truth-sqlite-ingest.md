# ADR D2: Raw JSONL as Ground Truth with Derived SQLite Ingest

## Status
Accepted

## Context
Trace generation is on the execution hot path. If a run crashes, timeouts occur, or execution is interrupted, data recorded up to the failure point must survive for post-mortem completeness analysis. Furthermore, analysis requires relational joins across spans and resource samples.

## Decision
Store raw trace data as an append-only JSON Lines (`.jsonl`) stream. Derive relational SQLite databases (`.sqlite`) during a post-run ingest phase.

## Alternatives Considered & Rejected
1. **Writing directly to SQLite during the run**:
   - *Rejected because*: Database locks, disk syncs, and table schema constraints create unpredictable event-loop lag and thread contention, polluting the timing of the very agent tasks being measured.
2. **Writing directly to Apache Parquet**:
   - *Rejected because*: Parquet is a columnar format designed for batch flushes. If an experiment crashes mid-run, an unclosed Parquet buffer is corrupted or lost. In addition, `pyarrow` adds a heavy external dependency.
