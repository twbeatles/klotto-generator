import sqlite3

try:
    from scripts.common import resolve_db_path
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.common import resolve_db_path

DB_PATH = resolve_db_path()

def verify():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM draws")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT * FROM draws ORDER BY draw_no DESC LIMIT 1")
        last_row = cursor.fetchone()
        
        print(f"Total rows: {count}")
        if last_row:
            print(f"Latest draw: {last_row}")
            
        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}")

if __name__ == "__main__":
    verify()
