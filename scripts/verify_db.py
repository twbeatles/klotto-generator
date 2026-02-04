import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lotto_history.db"

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
