import logging
from datetime import datetime, timedelta
from pathlib import Path
from ..db import get_db, ensure_tables
import sqlite3
import asyncio

class ActivityAgent:
    def __init__(self, config):
        self.config = config
        self._lock = asyncio.Lock()
        self.cooccurrence_window = timedelta(minutes=5)
        # Ensure tables exist
        ensure_tables()

    async def record_access(self, file_path: str) -> bool:
        """Record file access and potential co-occurrences."""
        try:
            async with self._lock:
                with get_db() as conn:
                    cursor = conn.cursor()
                    
                    # Get file_id
                    cursor.execute("SELECT id FROM files WHERE path = ?", (str(file_path),))
                    result = cursor.fetchone()
                    if not result:
                        logging.warning(f"No file record found for {file_path}")
                        return False
                    
                    file_id = result[0]
                    now = datetime.now()

                    # Update activity
                    cursor.execute("""
                        INSERT INTO file_activity (file_id, last_accessed, access_count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(file_id) DO UPDATE SET
                            last_accessed = ?,
                            access_count = access_count + 1
                    """, (file_id, now, now))

                    # Find recent accesses for co-occurrence
                    cursor.execute("""
                        SELECT file_id FROM file_activity
                        WHERE file_id != ? 
                        AND last_accessed >= datetime('now', '-5 minutes')
                    """, (file_id,))
                    
                    for row in cursor.fetchall():
                        other_id = row[0]
                        await self.record_cooccurrence(file_id, other_id)

                    return True

        except Exception as e:
            logging.error(f"Error recording file access: {e}", exc_info=True)
            return False

    async def record_cooccurrence(self, file_id_1: int, file_id_2: int):
        """Record or update file co-occurrence."""
        try:
            if file_id_1 == file_id_2:
                return
                
            # Ensure consistent ordering
            if file_id_1 > file_id_2:
                file_id_1, file_id_2 = file_id_2, file_id_1

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO file_cooccurrence (file_id_1, file_id_2, co_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(file_id_1, file_id_2) DO UPDATE SET
                        co_count = co_count + 1
                """, (file_id_1, file_id_2))

        except Exception as e:
            logging.error(f"Error recording co-occurrence: {e}")

    async def get_recent_activity(self, limit: int = 10):
        """Get recently accessed files."""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT f.path, fa.last_accessed, fa.access_count
                    FROM file_activity fa
                    JOIN files f ON fa.file_id = f.id
                    ORDER BY fa.last_accessed DESC
                    LIMIT ?
                """, (limit,))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error fetching recent activity: {e}")
            return []
