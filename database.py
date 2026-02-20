import sqlite3

DB_NAME = "chat.db"


def init_db():
    """Create database and table if not exists"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            bot TEXT NOT NULL
        )
        """)

        conn.commit()


def save_chat(user, bot):
    """Save one chat pair"""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()

            c.execute(
                "INSERT INTO chats (user, bot) VALUES (?, ?)",
                (user, bot)
            )

            conn.commit()

    except sqlite3.Error as e:
        print("DB Error:", e)
