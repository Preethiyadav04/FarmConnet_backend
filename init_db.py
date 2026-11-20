"""
FarmConnect - Database Initialization & Connection Test Utility
Reads credentials from backend/.env and ensures the MySQL database exists.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

def check_and_create_db():
    use_sqlite = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 't')
    if use_sqlite:
        print("[INFO] Project is configured to use SQLite (USE_SQLITE=True).")
        return True

    db_name = os.getenv('DB_NAME', 'farmconnect_db')
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_host = os.getenv('DB_HOST', '127.0.0.1')
    db_port = int(os.getenv('DB_PORT', '3306'))

    print("=" * 60)
    print(" FarmConnect - MySQL Connection & Database Verification")
    print("=" * 60)
    print(f" Host:     {db_host}:{db_port}")
    print(f" User:     {db_user}")
    print(f" Database: {db_name}")
    print(f" Password: {'[SET in .env]' if db_password else '[EMPTY in .env]'}")
    print("-" * 60)

    try:
        import MySQLdb
    except ImportError:
        try:
            import pymysql as MySQLdb
        except ImportError:
            print("[ERROR] Neither mysqlclient nor pymysql is installed.")
            return False

    # Attempt connection to MySQL server
    try:
        conn = MySQLdb.connect(
            host=db_host,
            user=db_user,
            passwd=db_password,
            port=db_port
        )
        cursor = conn.cursor()
        print(f"[SUCCESS] Connected to MySQL server at {db_host}:{db_port} successfully.")

        # Create database if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        print(f"[SUCCESS] Database '{db_name}' verified/created successfully.")
        cursor.close()
        conn.close()
        return True

    except MySQLdb.OperationalError as e:
        error_code, error_msg = e.args[0], e.args[1] if len(e.args) > 1 else str(e)
        print(f"[CONNECTION FAILED] Error {error_code}: {error_msg}")
        if error_code in (1045, 1698):
            print("\n-> Action Required: Update your DB_PASSWORD in 'FarmConnect/backend/.env'.")
        elif error_code in (2002, 2003):
            print(f"\n-> Action Required: MySQL server is not reachable on {db_host}:{db_port}. Verify that the MySQL service is running.")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected database connection error: {e}")
        return False

if __name__ == '__main__':
    success = check_and_create_db()
    sys.exit(0 if success else 1)
