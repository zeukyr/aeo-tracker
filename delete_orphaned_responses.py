"""
delete_orphaned_responses.py

Deletes rows in sentiment_responses (and, as a safety check, mention_responses)
whose question_id no longer exists in the questions table — i.e. rows left
behind after a question was deleted directly without cascading.

SAFETY MODEL (same pattern as the other fix scripts):
    1. Defaults to DRY RUN — only prints what would be deleted.
    2. Writes a full JSON backup of every row about to be deleted (not just
       IDs — the whole row), so it can be restored if needed.
    3. Only deletes with --apply.
    4. All deletes happen in a single transaction per table.

Usage:
    # 1. Dry run — see what would be deleted
    python delete_orphaned_responses.py

    # 2. Once you've checked the backup file and it's just the 4 duplicate
    #    questions' data, actually delete
    python delete_orphaned_responses.py --apply

    # 3. Roll back if needed
    python delete_orphaned_responses.py --restore backup_orphans_20260702T120000Z.json
    python delete_orphaned_responses.py --restore backup_orphans_20260702T120000Z.json --apply
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# Tables that reference questions.id via a question_id column.
# mention_responses is included as a safety check even though it's known
# to currently have zero orphans — if that ever changes, this will catch it.
TABLES_WITH_QUESTION_ID = ["sentiment_responses", "mention_responses"]


def get_connection():
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        sys.exit("Missing SUPABASE_DB_URL in environment/.env")
    return psycopg2.connect(url)


def fetch_orphaned_rows(conn, table: str):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT sr.* FROM {table} sr "
            f"LEFT JOIN questions q ON q.id = sr.question_id "
            f"WHERE sr.question_id IS NOT NULL AND q.id IS NULL"
        )
        return cur.fetchall()


def write_backup(orphans_by_table: dict):
    backup_path = f"backup_orphans_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    backup_data = {
        table: [dict(row) for row in rows]
        for table, rows in orphans_by_table.items()
    }
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, default=str)
    return backup_path


def delete_orphans(conn, table: str, ids: list):
    with conn.cursor() as cur:
        try:
            cur.execute(f"DELETE FROM {table} WHERE id = ANY(%s::uuid[])", [ids])
            conn.commit()
            return cur.rowcount, None
        except Exception as e:
            conn.rollback()
            return 0, str(e)


def run(apply: bool):
    conn = get_connection()
    try:
        orphans_by_table = {}
        for table in TABLES_WITH_QUESTION_ID:
            rows = fetch_orphaned_rows(conn, table)
            if rows:
                orphans_by_table[table] = rows

        if not orphans_by_table:
            print("No orphaned rows found in any table. Nothing to delete.")
            return

        total = 0
        for table, rows in orphans_by_table.items():
            print(f"\n{table}: {len(rows)} orphaned row(s) found")
            question_ids = sorted(set(str(r["question_id"]) for r in rows))
            print(f"  Distinct orphaned question_id(s): {len(question_ids)}")
            for qid in question_ids:
                print(f"    - {qid}")
            total += len(rows)

        print(f"\nTotal orphaned rows across all tables: {total}")

        backup_path = write_backup(orphans_by_table)
        print(f"\nFull backup of these rows written to {backup_path}")

        if not apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply to actually delete these rows.")
            return

        print(f"\nDeleting {total} orphaned rows...")
        for table, rows in orphans_by_table.items():
            ids = [r["id"] for r in rows]
            deleted_count, error = delete_orphans(conn, table, ids)
            if error:
                print(f"  {table}: FAILED — {error}")
            else:
                print(f"  {table}: deleted {deleted_count} row(s)")
    finally:
        conn.close()


def restore(backup_path: str, apply: bool):
    if not os.path.exists(backup_path):
        sys.exit(f"Backup file not found: {backup_path}")

    with open(backup_path, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    total = sum(len(rows) for rows in backup_data.values())
    if total == 0:
        print("Backup file is empty. Nothing to restore.")
        return

    print(f"Restoring {total} row(s) from {backup_path}:")
    for table, rows in backup_data.items():
        print(f"  {table}: {len(rows)} row(s)")

    if not apply:
        print("\nDRY RUN — nothing restored. Re-run with --apply to actually re-insert these rows.")
        return

    conn = get_connection()
    try:
        for table, rows in backup_data.items():
            if not rows:
                continue
            columns = list(rows[0].keys())
            col_list = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            with conn.cursor() as cur:
                try:
                    for row in rows:
                        values = [row[c] for c in columns]
                        cur.execute(
                            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                            f"ON CONFLICT (id) DO NOTHING",
                            values,
                        )
                    conn.commit()
                    print(f"  {table}: restored")
                except Exception as e:
                    conn.rollback()
                    print(f"  {table}: FAILED — {e}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry run)")
    parser.add_argument("--restore", metavar="BACKUP_FILE", help="Restore deleted rows from a backup file")
    args = parser.parse_args()

    if args.restore:
        restore(args.restore, args.apply)
    else:
        run(args.apply)


if __name__ == "__main__":
    main()