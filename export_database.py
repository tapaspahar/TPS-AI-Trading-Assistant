import json
import os
import sqlite3
from pathlib import Path

db_path = (
    Path(os.environ["LOCALAPPDATA"])
    / "TPS AI Trading Assistant"
    / "tps_ai.db"
)

output_path = Path("database") / "tps_ai_export.json"
output_path.parent.mkdir(parents=True, exist_ok=True)

print("Reading database:", db_path)

if not db_path.exists():
    raise FileNotFoundError(f"Database not found: {db_path}")

db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

try:
    tables = [
        row[0]
        for row in db.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]

    data = {}

    for table in tables:
        rows = db.execute(f'SELECT * FROM "{table}"').fetchall()
        data[table] = [dict(row) for row in rows]

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)

    print("Export completed.")
    print("Output:", output_path.resolve())
    print("Tables:", tables)

finally:
    db.close()