#!/usr/bin/env python3
"""Merge an exported legacy-browser data file into the local SQLite database."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import app_server

IMMUTABLE_FIELDS = {"id", "regNo", "password", "parentPassword", "passwordHash", "parentPasswordHash"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import edited browser-only portal data before the cloud migration.")
    parser.add_argument("export", type=Path, help="JSON file downloaded from the old portal on the original computer")
    parser.add_argument("--database", type=Path, default=Path("private_data/school.sqlite3"), help="local SQLite database")
    parser.add_argument("--seeds", type=Path, default=Path("private_data/seed_students.json"), help="original baseline student seed file")
    args = parser.parse_args()

    try:
        legacy = json.loads(args.export.read_text(encoding="utf-8"))
        seed = json.loads(args.seeds.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read the export or baseline data: {exc}", file=sys.stderr)
        return 2
    if isinstance(legacy, dict) and legacy.get("format") == "jvm-shyamali-local-export-v1":
        legacy = legacy.get("records")
    if not isinstance(legacy, dict) or not isinstance(seed, dict):
        print("Expected the export and baseline to contain student-record objects.", file=sys.stderr)
        return 2

    database = args.database.expanduser().resolve()
    if not database.is_file():
        print(f"SQLite database not found: {database}", file=sys.stderr)
        return 2
    source_count = len(legacy)
    expected = f"IMPORT {source_count} EXPORTED RECORDS"
    print(f"Exported records: {source_count}")
    print("Only changed fields on existing seeded records will be merged. Password fields and unknown IDs are ignored.")
    if input(f"Type {expected} to continue: ").strip() != expected:
        print("Import cancelled; the database was not changed.")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = database.with_name(f"{database.stem}.before-browser-import-{stamp}{database.suffix}")
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    changed_records = skipped_records = skipped_fields = 0
    try:
        with sqlite3.connect(backup) as backup_con:
            con.backup(backup_con)
        app_server.ensure_sqlite_schema(con)
        baseline_count = con.execute("SELECT COUNT(*) FROM seed_records").fetchone()[0]
        if not baseline_count:
            database_ids = {row[0] for row in con.execute("SELECT student_id FROM records")}
            if database_ids != set(seed):
                raise RuntimeError("The SQLite records and baseline seed do not have matching IDs.")
            con.executemany("INSERT INTO seed_records(student_id,payload) VALUES(?,?)",
                            [(sid, json.dumps(app_server.sanitize_student(rec), ensure_ascii=False))
                             for sid, rec in seed.items()])
        con.commit()
        con.execute("BEGIN IMMEDIATE")
        before_count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        for sid, old_record in legacy.items():
            baseline_record = seed.get(sid)
            if not isinstance(baseline_record, dict) or not isinstance(old_record, dict):
                skipped_records += 1
                continue
            baseline = app_server.sanitize_student(baseline_record)
            clean = app_server.sanitize_student(old_record)
            changed = {}
            for key, value in clean.items():
                if key in IMMUTABLE_FIELDS:
                    continue
                if key not in baseline:
                    skipped_fields += 1
                elif value != baseline[key]:
                    changed[key] = value
            row = con.execute("SELECT payload FROM records WHERE student_id=?", (sid,)).fetchone()
            if not row:
                skipped_records += 1
                continue
            if changed:
                current = json.loads(row["payload"])
                current.update(changed)
                con.execute("UPDATE records SET payload=?,updated_at=? WHERE student_id=?",
                            (json.dumps(app_server.sanitize_student(current), ensure_ascii=False), app_server.utc_now(), sid))
                con.execute("INSERT INTO audit_log(occurred_at,actor_role,actor_id,action,student_id,changed_fields) VALUES(?,?,?,?,?,?)",
                            (app_server.utc_now(), "migration", "legacy-browser-export", "legacy-localstorage-import",
                             sid, json.dumps(list(changed))))
                changed_records += 1
        after_count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        if before_count != after_count:
            raise RuntimeError("Record count changed unexpectedly; rolling back the import.")
        con.commit()
    except Exception as exc:
        con.rollback()
        print(f"Import failed ({type(exc).__name__}); the database was rolled back.", file=sys.stderr)
        return 1
    finally:
        con.close()

    print("Import complete:")
    print(f"  changed records: {changed_records}")
    print(f"  skipped records: {skipped_records}")
    print(f"  skipped fields: {skipped_fields}")
    print(f"  safety copy: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
