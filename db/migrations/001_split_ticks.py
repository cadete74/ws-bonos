from __future__ import annotations

"""
Migration 001 — split combined ticks into per-symbol rows.

Safe to run multiple times (idempotent guard on ticks_legacy).
Run via: make migrate-ticks   (or: DB_PATH=./data/wsbonos.sqlite3 python3 db/migrations/001_split_ticks.py)

Steps:
  1. Guard: if ticks_legacy exists → already migrated, exit 0.
  2. BEGIN.
  3. ALTER TABLE ticks RENAME TO ticks_legacy.
  4. CREATE new per-symbol ticks table + indexes.
  5. INSERT splitting each legacy combined row into 2 per-symbol rows.
  6. Reconcile: assert count(ticks) == 2 * count(ticks_legacy). Mismatch → ROLLBACK, exit 1.
  7. DROP VIEW IF EXISTS ticks_rows.
  8. COMMIT.

Rollback (if needed after a bad run):
  sqlite3 <db> "DROP TABLE IF EXISTS ticks; ALTER TABLE ticks_legacy RENAME TO ticks;"
  Then revert the code changes.
"""

import os
import sqlite3
import sys


DB_PATH = os.getenv("DB_PATH", "./data/wsbonos.sqlite3")


def main() -> None:
    print(f"Migration 001 — target DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        # Step 1: Guard — check if already migrated.
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ticks_legacy'"
        )
        if cur.fetchone():
            print("Already migrated (ticks_legacy table exists). Exiting 0.")
            conn.close()
            sys.exit(0)

        # Step 2: begin transaction.
        conn.execute("BEGIN")

        # Step 3: rename existing combined table to backup.
        conn.execute("ALTER TABLE ticks RENAME TO ticks_legacy")
        print("  ticks → ticks_legacy (backup created)")

        # Step 4: create new per-symbol schema.
        conn.execute("""
            CREATE TABLE ticks (
              id       INTEGER PRIMARY KEY AUTOINCREMENT,
              ts       TEXT    NOT NULL,
              symbol   TEXT    NOT NULL,
              last     REAL,
              vol      REAL,
              turnover REAL,
              source   TEXT,
              UNIQUE(ts, symbol)
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX ux_ticks_ts_symbol ON ticks(ts, symbol)"
        )
        conn.execute(
            "CREATE INDEX idx_ticks_symbol_ts_desc ON ticks(symbol, ts DESC)"
        )
        print("  New ticks table + indexes created")

        # Step 5: insert split rows.
        conn.execute("""
            INSERT INTO ticks(ts, symbol, last, vol, turnover, source)
            SELECT ts, 'AL30', al30, vol_al30, turn_al30, source
            FROM ticks_legacy
            UNION ALL
            SELECT ts, 'GD30', gd30, vol_gd30, turn_gd30, source
            FROM ticks_legacy
        """)
        print("  Rows split and inserted")

        # Step 6: reconcile row counts.
        legacy_count: int = conn.execute(
            "SELECT COUNT(*) FROM ticks_legacy"
        ).fetchone()[0]
        new_count: int = conn.execute(
            "SELECT COUNT(*) FROM ticks"
        ).fetchone()[0]
        expected = 2 * legacy_count

        print(f"  Reconcile: legacy={legacy_count}, new={new_count}, expected={expected}")
        if new_count != expected:
            conn.execute("ROLLBACK")
            print(
                f"MIGRATION FAILED — row count mismatch: expected {expected}, got {new_count}. "
                "Rolled back. ticks_legacy is intact."
            )
            conn.close()
            sys.exit(1)

        # Step 7: drop the compatibility view (it references the old schema).
        conn.execute("DROP VIEW IF EXISTS ticks_rows")
        print("  ticks_rows view dropped")

        # Step 8: commit.
        conn.execute("COMMIT")
        print(f"Migration 001 COMPLETE — {new_count} rows in ticks ({legacy_count} legacy rows backed up).")
        print("Run `SELECT COUNT(*) FROM ticks; SELECT COUNT(*) FROM ticks_legacy;` to verify.")
        conn.close()

    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        conn.close()
        print(f"MIGRATION FAILED with exception: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
