import sqlite3

def view_database(db_file):
    """
    Connects to an SQLite database and prints the table names and their contents.
    """
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Get a list of all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print(f"No tables found in '{db_file}'.")
            return

        print(f"Tables in '{db_file}':")
        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            print(f"\n--- Table: {table_name} ---")

            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [info[1] for info in cursor.fetchall()]
            print(f"Columns: {', '.join(columns)}")

            # Fetch and print a few rows from the table
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5;")
                rows = cursor.fetchall()

                if not rows:
                    print("Table is empty.")
                else:
                    print("First 5 rows:")
                    for row in rows:
                        print(row)
            except sqlite3.OperationalError as e:
                print(f"Could not read from table {table_name}: {e}")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    database_file = 'cases.db'
    view_database(database_file)
