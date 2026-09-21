import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "facevault.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Drop the unique constraint index
cur.execute("DROP INDEX IF EXISTS uq_attendance_employee_date")

# 2. Create high-performance composite index on (employee_id, date)
cur.execute("CREATE INDEX IF NOT EXISTS ix_attendances_employee_date ON attendances (employee_id, date)")

conn.commit()

# Verify
cur.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name='attendances'")
rows = cur.fetchall()
print("Indexes on attendances table:")
for r in rows:
    print(f" - {r[0]}: {r[1]} -> {r[2]}")

cur.execute("SELECT COUNT(*) FROM attendances")
count = cur.fetchone()[0]
print(f"Total existing attendance rows preserved: {count}")

conn.close()
print("Migration completed successfully!")

