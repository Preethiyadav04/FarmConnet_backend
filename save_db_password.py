"""
FarmConnect - Secure Local Database Credential Updater
Prompts for password securely using getpass.
Verifies connection to MySQL 8.0 on 127.0.0.1:3306.
If verified, updates DB_PASSWORD in backend/.env automatically and securely.
Never echoes or displays the password.
"""

import getpass
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'

def set_mysql_password():
    print("=" * 65)
    print(" FarmConnect - Secure Database Credential Setup")
    print("=" * 65)
    print("Target Server: 127.0.0.1:3306 (MySQL 8.0)")
    print("Target DB:     farmconnect_db")
    print("-" * 65)

    try:
        import MySQLdb
    except ImportError:
        print("[ERROR] mysqlclient is not available.")
        return False

    password = getpass.getpass("Enter your MySQL root password (input hidden): ")
    if not password:
        print("[ERROR] Password cannot be empty.")
        return False

    # Test connection to MySQL 8.0 on port 3306
    print("\nVerifying password against MySQL 8.0 on port 3306...")
    try:
        conn = MySQLdb.connect(
            host="127.0.0.1",
            user="root",
            passwd=password,
            port=3306,
            connect_timeout=5
        )
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION(), @@port;")
        ver, port = cursor.fetchone()
        cursor.close()
        conn.close()
        print(f"[SUCCESS] Connected to MySQL {ver} on port {port}!")
    except MySQLdb.OperationalError as e:
        print(f"[FAILED] Could not connect to MySQL: {e.args[1] if len(e.args) > 1 else e}")
        return False
    except Exception as e:
        print(f"[FAILED] Unexpected error: {e}")
        return False

    # Update backend/.env securely
    try:
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        updated_lines = []
        replaced = False
        for line in lines:
            if line.startswith('DB_PASSWORD='):
                updated_lines.append(f"DB_PASSWORD={password}\n")
                replaced = True
            elif line.startswith('DB_PORT='):
                updated_lines.append("DB_PORT=3306\n")
            elif line.startswith('USE_SQLITE='):
                updated_lines.append("USE_SQLITE=False\n")
            else:
                updated_lines.append(line)

        if not replaced:
            updated_lines.append(f"DB_PASSWORD={password}\n")

        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)

        print("[SUCCESS] backend/.env has been successfully updated with verified MySQL 8.0 credentials!")
        print("Ready for Django migrations.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update .env: {e}")
        return False

if __name__ == '__main__':
    ok = set_mysql_password()
    sys.exit(0 if ok else 1)
