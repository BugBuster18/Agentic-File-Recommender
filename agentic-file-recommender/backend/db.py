import sqlite3
import pathlib
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Generator

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "files.db"

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Thread-safe database connection manager with WAL mode."""
    conn = sqlite3.connect(
        DB_PATH, 
        timeout=60,
        check_same_thread=False,
        isolation_level=None  # Enable autocommit mode
    )
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        yield conn
    finally:
        conn.commit()
        conn.close()

def is_db_initialized() -> bool:
    """Check if database exists and has required tables."""
    if not DB_PATH.exists():
        return False
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('files', 'file_content')
            """)
            tables = cursor.fetchall()
            return len(tables) == 2
    except Exception:
        return False

def ensure_tables():
    """Ensure all required tables exist."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                -- Activity tracking tables
                CREATE TABLE IF NOT EXISTS file_activity (
                    file_id INTEGER PRIMARY KEY,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS file_cooccurrence (
                    file_id_1 INTEGER,
                    file_id_2 INTEGER,
                    co_count INTEGER DEFAULT 0,
                    PRIMARY KEY (file_id_1, file_id_2),
                    FOREIGN KEY(file_id_1) REFERENCES files(id),
                    FOREIGN KEY(file_id_2) REFERENCES files(id)
                );

                CREATE INDEX IF NOT EXISTS idx_file_activity_access ON file_activity(last_accessed);
                CREATE INDEX IF NOT EXISTS idx_cooccurrence_counts ON file_cooccurrence(co_count);
            """)
            logging.info("Activity tables verified")
            return True
    except Exception as e:
        logging.error(f"Failed to create activity tables: {e}", exc_info=True)
        return False

def init_db(force: bool = False):
    """Initialize SQLite database with required tables."""
    try:
        DB_PATH.parent.mkdir(exist_ok=True)
        
        if force and DB_PATH.exists():
            try:
                DB_PATH.unlink()
                logging.info("Deleted existing database")
            except Exception as e:
                logging.error(f"Failed to delete existing database: {e}")
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Core tables
            cursor.executescript("""
            PRAGMA foreign_keys = ON;
            
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                hash TEXT NOT NULL,
                file_type TEXT NOT NULL,
                last_modified DATETIME NOT NULL,
                last_scanned DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS file_content (
                file_id INTEGER PRIMARY KEY,
                content_preview TEXT,
                embedding_vector BLOB,
                FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);
            """)
            
            logging.info("Core tables created successfully")
        
        # Create activity tables
        if not ensure_tables():
            raise RuntimeError("Failed to create activity tables")
        
        logging.info("Database initialized successfully")
        return True
        
    except Exception as e:
        logging.error(f"Database initialization failed: {e}", exc_info=True)
        raise RuntimeError(f"Database initialization failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        init_db(force=True)
        logging.info("Database ready")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        exit(1)
