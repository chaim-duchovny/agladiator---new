import mysql.connector
from mysql.connector import Error

connection = None

try:
    # Connect to MySQL server (no database specified)
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        password=''
    )

    if connection.is_connected():
        print("Connected to MySQL server")

        # Create a cursor object
        cursor = connection.cursor()

        # Create a new database
        cursor.execute("CREATE DATABASE IF NOT EXISTS register")
        print("Database 'register' created (if it did not exist)")

        # Show all databases to confirm
        cursor.execute("SHOW DATABASES")
        for db in cursor:
            print(db)
        
        cursor.close()
        connection.close()

        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='register'
        )

        cursor = connection.cursor()

        # Create a new table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL,
                password VARCHAR(255),
                elo INT DEFAULT 1500,
                agentFile VARCHAR(255)
            )
        """)
        print("Table 'users' created (if it did not exist)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                player1_id INT NOT NULL,
                player2_id INT,
                status ENUM('waiting', 'active', 'completed') DEFAULT 'waiting',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player1_id) REFERENCES users(id),
                FOREIGN KEY (player2_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN current_match INT REFERENCES matches(id);
            """)  # [4]

        # Add to db.py after creating users and matches tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                start_date DATETIME,
                end_date DATETIME,
                status ENUM('upcoming', 'active', 'completed') DEFAULT 'upcoming',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                max_participants INT NOT NULL,
                current_participants INT DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournament_participants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tournament_id INT NOT NULL,
                user_id INT NOT NULL,
                seed INT,
                status ENUM('active', 'eliminated') DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournament_matches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tournament_id INT NOT NULL,
                match_id INT NOT NULL,
                round INT NOT NULL,
                position INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id),
                FOREIGN KEY (match_id) REFERENCES matches(id)
            )
        """)


except Error as e:
    print("Error while connecting to MySQL", e)

finally:
    if connection is not None and connection.is_connected():
        connection.close()
        print("MySQL connection is closed")



