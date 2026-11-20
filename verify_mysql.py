"""
FarmConnect - Safe Local MySQL Verification Utility
Prompts for password securely without echoing to screen.
Tests both port 3306 (MySQL 8.0) and port 3307 (MySQL 8.4).
Never logs, displays, or exposes passwords.
Does not alter or delete any databases.
"""

import getpass
import sys

def test_mysql_connection():
    print("=" * 65)
    print(" FarmConnect - Safe Local MySQL Verification")
    print("=" * 65)
    print("This utility will test your password against both detected MySQL instances:")
    print("  • Port 3306 -> Service 'MySQL80' (MySQL Server 8.0)")
    print("  • Port 3307 -> Service 'MySQL84' (MySQL Server 8.4)")
    print("-" * 65)

    try:
        import MySQLdb
    except ImportError:
        print("[ERROR] mysqlclient is not available in the current environment.")
        return

    # Prompt securely using getpass - characters will NOT be echoed
    try:
        password = getpass.getpass("Enter your MySQL root password (input will be hidden): ")
    except Exception as e:
        print(f"[ERROR] Could not read input: {e}")
        return

    ports_to_test = [
        (3306, "MySQL Server 8.0 (Service: MySQL80)"),
        (3307, "MySQL Server 8.4 (Service: MySQL84)")
    ]

    working_port = None
    existing_databases = []

    for port, label in ports_to_test:
        print(f"\nTesting connection to {label} on port {port}...")
        try:
            conn = MySQLdb.connect(
                host="127.0.0.1",
                user="root",
                passwd=password,
                port=port,
                connect_timeout=5
            )
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION();")
            version = cursor.fetchone()[0]

            cursor.execute("SHOW DATABASES;")
            dbs = [row[0] for row in cursor.fetchall()]

            cursor.close()
            conn.close()

            print(f"  [SUCCESS] Connected to {label} successfully!")
            print(f"  Server Version: {version}")
            print(f"  Existing Databases: {', '.join(dbs)}")

            if working_port is None:
                working_port = port
                existing_databases = dbs

        except MySQLdb.OperationalError as e:
            error_code = e.args[0] if len(e.args) > 0 else 0
            if error_code in (1045, 1698):
                print(f"  [ACCESS DENIED] Password was incorrect for root on port {port}.")
            elif error_code in (2002, 2003):
                print(f"  [OFFLINE] Port {port} is not accepting connections.")
            else:
                print(f"  [FAILED] Connection error on port {port} (Error code: {error_code})")
        except Exception as e:
            print(f"  [FAILED] Unexpected error on port {port}: {e}")

    print("\n" + "=" * 65)
    print(" VERIFICATION SUMMARY")
    print("=" * 65)

    if working_port is not None:
        print(f"Your MySQL server is accessible on PORT: {working_port}")
        has_farmconnect_db = 'farmconnect_db' in existing_databases
        print(f"Database 'farmconnect_db' exists: {'YES' if has_farmconnect_db else 'NO (can be created safely)'}")
        print("\nRecommended settings for 'FarmConnect/backend/.env':")
        print(f"  DB_ENGINE=django.db.backends.mysql")
        print(f"  DB_NAME=farmconnect_db")
        print(f"  DB_USER=root")
        print(f"  DB_PASSWORD=[your verified password]")
        print(f"  DB_HOST=127.0.0.1")
        print(f"  DB_PORT={working_port}")
        print(f"  USE_SQLITE=False")
    else:
        print("None of the ports accepted the password you entered.")
        print("Suggestions:")
        print(" 1. Double check for caps lock or special characters.")
        print(" 2. If you remember another possible password, run this script again.")
        print(" 3. Alternatively, you can use SQLite (USE_SQLITE=True) without needing any password.")
    print("=" * 65)

if __name__ == '__main__':
    test_mysql_connection()
