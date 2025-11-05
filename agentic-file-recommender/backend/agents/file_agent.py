import pathlib
from datetime import datetime
import logging
import asyncio
from ..utils import compute_file_hash, extract_text_snippet, get_file_type
from ..db import get_db

class FileAgent:
    def __init__(self, config):
        self.config = config
        self.recommendation_agent = None
        self._lock = asyncio.Lock()

    def set_recommendation_agent(self, agent):
        """Set the recommendation agent for embedding computation."""
        self.recommendation_agent = agent
        logging.info("Recommendation agent set successfully")

    async def scan_directory(self, root_path: str):
        """Scan directory and update database with proper locking."""
        try:
            root = pathlib.Path(root_path)
            if not root.exists():
                raise ValueError(f"Directory not found: {root_path}")
            if not root.is_dir():
                raise ValueError(f"Path must be a directory: {root_path}")

            async with self._lock:
                for path in root.rglob("*"):
                    if not path.is_file() or path.suffix.lower() not in self.config["scan"]["allowed_exts"]:
                        continue

                    try:
                        # New DB connection per file
                        with get_db() as conn:
                            cursor = conn.cursor()
                            file_hash = compute_file_hash(path)
                            file_type = get_file_type(path)
                            
                            cursor.execute("""
                                INSERT OR REPLACE INTO files 
                                (path, hash, file_type, last_modified, last_scanned)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                str(path),
                                file_hash,
                                file_type,
                                datetime.fromtimestamp(path.stat().st_mtime),
                                datetime.now()
                            ))
                            
                            file_id = cursor.lastrowid
                            
                            text = extract_text_snippet(path, self.config["scan"]["snippet_bytes"])
                            if text and self.recommendation_agent:
                                await self.recommendation_agent.store_embedding(file_id, text)
                                
                    except Exception as e:
                        logging.error(f"Error processing file {path}: {e}")
                        continue

            logging.info(f"Completed scanning directory: {root_path}")
            return True

        except Exception as e:
            logging.error(f"Error scanning directory {root_path}: {e}")
            raise
