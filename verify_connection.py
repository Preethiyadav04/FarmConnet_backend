"""
FarmConnect - Safe MySQL 8.0 Connection & Schema Inspector
Never prints or logs passwords.
Inspects database version, port, active database, existing tables, and verifies connection.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

def inspect_and_verify():
    db_engine = os.getenv('DB_ENGINE', 'django.db.backends.mysql')
    db_name = os.getenv('DB_NAME', 'farmconnect_db')
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_host = os.getenv('DB_HOST', '127.0.0.1')
    db_port = int(os.getenv('DB_PORT', '3306'))
    use_sqlite = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 't')

    print("=" * 65)
    print(" FarmConnect - MySQL 8.0 Connection & Schema Inspector")
    print("=" * 65)
    print(f" Engine:      {db_engine}")
    print(f" Target DB:   {db_name}")
    print(f" User:        {db_user}")
    print(f" Host:        {db_host}")
    print(f" Port:        {db_port}")
    print(f" USE_SQLITE:  {use_sqlite}")
    print(f" Password:    {'[SET / CONFIGURED (PROTECTED)]' if db_password else '[EMPTY]'}")
    print("-" * 65)

    if use_sqlite:
        print("[ERROR] USE_SQLITE is set to True. Please ensure USE_SQLITE=False.")
        return False

    if not db_password:
        print("[ERROR] DB_PASSWORD is empty in backend/.env.")
        return False

    try:
        import MySQLdb
    except ImportError:
        print("[ERROR] mysqlclient (MySQLdb) is not installed.")
        return False

    # Connect to MySQL server on host:port
    try:
        conn = MySQLdb.connect(
            host=db_host,
            user=db_user,
            passwd=db_password,
            port=db_port,
            connect_timeout=5
        )
        cursor = conn.cursor()

        # Check all databases
        cursor.execute("SHOW DATABASES;")
        all_dbs = [row[0] for row in cursor.fetchall()]

        # Ensure farmconnect_db exists safely
        if db_name not in all_dbs:
            print(f"Database '{db_name}' does not exist yet. Creating safely...")
            cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            print(f"[SUCCESS] Database '{db_name}' created safely.")
        else:
            print(f"Database '{db_name}' already exists.")

        cursor.close()
        conn.close()

        # Connect directly to farmconnect_db
        conn_db = MySQLdb.connect(
            host=db_host,
            user=db_user,
            passwd=db_password,
            db=db_name,
            port=db_port,
            connect_timeout=5
        )
        cursor_db = conn_db.cursor()

        # Execute query: SELECT VERSION(), @@port, DATABASE();
        cursor_db.execute("SELECT VERSION(), @@port, DATABASE();")
        version, active_port, current_db = cursor_db.fetchone()

        print("\n" + "-" * 65)
        print(" VERIFIED DATABASE ENGINE PARAMETERS:")
        print(f"   • MySQL Version:  {version}")
        print(f"   • Active Port:    {active_port}")
        print(f"   • Connected DB:   {current_db}")
        print("-" * 65)

        # Inspect existing tables before making changes
        cursor_db.execute("SHOW TABLES;")
        tables = [row[0] for row in cursor_db.fetchall()]

        print(f"\n[SCHEMA INSPECTION] Existing tables in '{current_db}':")
        if tables:
            print(f"  Total tables found: {len(tables)}")
            for t in tables:
                print(f"    - {t}")
        else:
            print("  Total tables found: 0 (Clean database, ready for initial migrations)")

        cursor_db.close()
        conn_db.close()

        print("\n" + "=" * 65)
        print(" PRE-MIGRATION SAFETY CHECK PASSED!")
        print("=" * 65)
        return True

    except MySQLdb.OperationalError as e:
        error_code = e.args[0] if len(e.args) > 0 else 0
        error_msg = e.args[1] if len(e.args) > 1 else str(e)
        print(f"[CONNECTION FAILED] Error {error_code}: {error_msg}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False

if __name__ == '__main__':
    ok = inspect_and_verify()
    sys.exit(0 if ok else 1)
