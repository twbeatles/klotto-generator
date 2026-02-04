import sqlite3
import requests
import json
import time
import os
from pathlib import Path
from datetime import datetime

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lotto_history.db"
API_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={}"

def init_db():
    """Initialize the database and create the table if it doesn't exist."""
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created data directory: {DATA_DIR}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS draws (
        draw_no INTEGER PRIMARY KEY,
        date TEXT,
        num1 INTEGER,
        num2 INTEGER,
        num3 INTEGER,
        num4 INTEGER,
        num5 INTEGER,
        num6 INTEGER,
        bonus INTEGER,
        prize_amount INTEGER,
        winners_count INTEGER,
        total_sales INTEGER
    )
    ''')
    
    conn.commit()
    return conn

def get_last_draw_no(conn):
    """Get the last stored draw number from the database."""
    cursor = conn.cursor()
    cursor.execute('SELECT MAX(draw_no) FROM draws')
    result = cursor.fetchone()
    return result[0] if result[0] else 0

def fetch_draw(draw_no):
    """Fetch draw data from the official API."""
    url = API_URL.format(draw_no)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.dhlottery.co.kr/lt645/result',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
        }
        # Disable SSL warning for testing if verification fails
        requests.packages.urllib3.disable_warnings() 
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            try:
                data = response.json()
            except json.JSONDecodeError:
                print(f"Draw {draw_no} response is not JSON: {response.text[:100]}...")
                return None

            if data.get('returnValue') == 'success':
                return data
            elif 'data' in data: # Handle potential new format
                 return data
            else:
                 print(f"Draw {draw_no} API failure: {data}")
                 return data # Return data anyway to let save_draw decide or check returnValue
        else:
            print(f"Draw {draw_no} status code: {response.status_code}")

    except Exception as e:
        print(f"Error fetching draw {draw_no}: {e}")
    return None

def save_draw(conn, data):
    """Save a single draw record to the database."""
    # Handle new format extraction if necessary, but standard API usually returns:
    # drwNo, drwtNo1, ..., drwNoDate
    
    # Check if it's the new nested format (defensive coding based on client.py)
    if 'data' in data and 'list' in data['data']:
         item = data['data']['list'][0]
         # Mapping from client.py
         record = (
            item.get('ltEpsd'),
            item.get('ltRflYmd'), # Format might need adjustment
            item.get('tm1WnNo'),
            item.get('tm2WnNo'),
            item.get('tm3WnNo'),
            item.get('tm4WnNo'),
            item.get('tm5WnNo'),
            item.get('tm6WnNo'),
            item.get('bnsWnNo'),
            item.get('rnk1WnAmt', 0),
            item.get('rnk1WnNope', 0),
            item.get('rlvtEpsdSumNtslAmt', 0)
        )
         # Date format fix: YYYYMMDD -> YYYY-MM-DD
         date_str = str(record[1])
         if len(date_str) == 8:
             fixed_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
             record = (*record[:1], fixed_date, *record[2:])
            
    else:
        # Standard legacy format
        record = (
            data.get('drwNo'),
            data.get('drwNoDate'),
            data.get('drwtNo1'),
            data.get('drwtNo2'),
            data.get('drwtNo3'),
            data.get('drwtNo4'),
            data.get('drwtNo5'),
            data.get('drwtNo6'),
            data.get('bnusNo'),
            data.get('firstWinamnt'),
            data.get('firstPrzwnerCo'),
            data.get('totSellamnt')
        )

    try:
        sql = '''INSERT OR REPLACE INTO draws 
                 (draw_no, date, num1, num2, num3, num4, num5, num6, bonus, prize_amount, winners_count, total_sales)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        conn.execute(sql, record)
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def main():
    print("Starting Lotto History Scraper...")
    conn = init_db()
    
    last_draw = get_last_draw_no(conn)
    print(f"Last recorded draw: {last_draw}")
    
    current_draw = last_draw + 1
    consecutive_failures = 0
    MAX_FAILURES = 3 
    
    while True:
        print(f"Fetching draw #{current_draw}...", end=" ", flush=True)
        data = fetch_draw(current_draw)
        
        if data:
            # Check if valid return
            # Standard API returns fail if draw not happened yet
            if data.get('returnValue') == 'fail':
                 print("Not yet drawn or invalid.")
                 consecutive_failures += 1
            else:
                 if save_draw(conn, data):
                     print("Success!")
                     consecutive_failures = 0
                 else:
                     print("Failed to save.")
                     consecutive_failures += 1
        else:
            print("Network error or invalid response.")
            consecutive_failures += 1
            
        if consecutive_failures >= MAX_FAILURES:
            print(f"Stopping after {consecutive_failures} consecutive failures. Assuming end of history reached.")
            break
            
        current_draw += 1
        time.sleep(0.2) # Be polite to the server

    print("Scraping completed.")
    
    # Print summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM draws")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT MAX(draw_no) FROM draws")
    max_no = cursor.fetchone()[0]
    print(f"Total records: {count}")
    print(f"Latest draw: {max_no}")
    
    conn.close()

if __name__ == "__main__":
    main()
