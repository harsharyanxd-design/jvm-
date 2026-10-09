#!/usr/bin/env python3
"""Copy the existing SQLite portal database into an empty PostgreSQL database."""
from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
from pathlib import Path

import app_server

TABLE_COLUMNS = {
    "records": ("student_id", "payload", "updated_at"),
    "users": ("role", "login_id", "salt", "password_hash", "student_id", "metadata", "aliases"),
    "audit_log": ("id", "occurred_at", "actor_role", "actor_id", "action", "student_id", "changed_fields"),
    "enquiries": ("id", "created_at", "name", "email", "message", "status"),
}


def source_connection(path: Path):
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite source was not found: {resolved}")
    return sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)


def counts(connection, tables, postgres=False):
    result = {}
    for table in tables:
        if postgres:
            result[table] = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        else:
            result[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return result


def migrate(source_path: Path, seeds_path: Path, target_url: str) -> dict[str, int]:
    source = source_connection(source_path)
    try:
        target = app_server.postgres_conn(target_url)
    except Exception:
        source.close()
        raise
    committed = False
    try:
        seed_students = json.loads(seeds_path.expanduser().read_text(encoding="utf-8"))
        if not isinstance(seed_students, dict):
            raise RuntimeError("Student baseline seed must be a record object.")
        source_tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(TABLE_COLUMNS) - source_tables
        if missing:
            raise RuntimeError("SQLite database is missing required tables: " + ", ".join(sorted(missing)))

        app_server.ensure_postgres_schema(target)
        existing = counts(target, TABLE_COLUMNS, postgres=True)
        existing_baseline = target.execute("SELECT COUNT(*) AS count FROM seed_records").fetchone()["count"]
        if any(existing.values()) or existing_baseline:
            raise RuntimeError("The PostgreSQL destination is not empty. Refusing to merge or overwrite records.")

        source_counts = counts(source, TABLE_COLUMNS)
        if source_counts["records"] == 0 or source_counts["users"] == 0:
            raise RuntimeError("The SQLite source has no portal records or accounts.")
        source_ids = {row[0] for row in source.execute("SELECT student_id FROM records")}
        if source_ids != set(seed_students):
            raise RuntimeError("The SQLite records and original seed baseline do not have matching IDs.")

        print("Source rows to copy:")
        for table, count in source_counts.items():
            print(f"  {table}: {count}")
        expected = f"IMPORT {source_counts['records']} RECORDS"
        if input(f"Type {expected} to continue: ").strip() != expected:
            raise RuntimeError("Migration cancelled; no data was copied.")

        target.executemany("INSERT INTO seed_records(student_id,payload) VALUES(%s,%s)",
                           [(sid, json.dumps(app_server.sanitize_student(rec), ensure_ascii=False))
                            for sid, rec in seed_students.items()])

        for table, columns in TABLE_COLUMNS.items():
            rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
            if rows:
                placeholders = ", ".join("%s" for _ in columns)
                target.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    [tuple(row) for row in rows],
                )

        for table in ("audit_log", "enquiries"):
            max_id = target.execute(f"SELECT MAX(id) AS max_id FROM {table}").fetchone()["max_id"]
            if max_id is not None:
                target.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)",
                    (table, max_id),
                )

        copied = counts(target, TABLE_COLUMNS, postgres=True)
        copied_baseline = target.execute("SELECT COUNT(*) AS count FROM seed_records").fetchone()["count"]
        if copied != source_counts or copied_baseline != len(seed_students):
            raise RuntimeError(f"Row-count verification failed (source={source_counts}, destination={copied}).")
        target.commit()
        committed = True
        return {**copied, "seed_records": copied_baseline}
    finally:
        if not committed:
            target.rollback()
        target.close()
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely migrate JVM Shyamali SQLite data to PostgreSQL.")
    parser.add_argument("--source", type=Path, default=Path("private_data/school.sqlite3"),
                        help="read-only source SQLite file (default: private_data/school.sqlite3)")
    parser.add_argument("--seeds", type=Path, default=Path("private_data/seed_students.json"),
                        help="private original student baseline (default: private_data/seed_students.json)")
    args = parser.parse_args()
    target_url = getpass.getpass("Paste the PostgreSQL URL (input is hidden): ").strip()
    if not target_url.startswith(("postgres://", "postgresql://")):
        print("Expected a postgres:// or postgresql:// connection URL.", file=sys.stderr)
        return 2
    try:
        result = migrate(args.source, args.seeds, target_url)
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"Migration stopped: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Migration stopped ({type(exc).__name__}). Check the PostgreSQL URL, network access, and installed driver.", file=sys.stderr)
        return 1
    print("Migration committed and verified:")
    for table, count in result.items():
        print(f"  {table}: {count}")
    print("The SQLite source was opened read-only and left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
