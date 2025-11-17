from sentence_transformers import SentenceTransformer
from annoy import AnnoyIndex
import numpy as np
import logging
from pathlib import Path
from typing import List, Dict
from ..db import get_db
from ..utils import extract_text_snippet
import sqlite3
import time
import asyncio
from datetime import datetime, timedelta
import math
import random

class RecommendationAgent:
    def __init__(self, config):
        if not config or "embeddings" not in config:
            raise ValueError("Invalid config: missing embeddings section")
            
        self.config = config
        self.model_name = config["embeddings"].get("model_name", "all-MiniLM-L6-v2")
        self.dim = config["embeddings"].get("dim", 384)
        
        try:
            self.model = SentenceTransformer(self.model_name)
        except Exception as e:
            logging.error(f"Failed to load SentenceTransformer model: {e}")
            raise
            
        self.index = AnnoyIndex(self.dim, 'angular')
        self.file_id_map = {}
        self._load_embeddings()

    def _load_embeddings(self):
        """Load embeddings with error handling."""
        try:
            with get_db() as conn:
                conn.row_factory = sqlite3.Row  # Enable dictionary access
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT f.id, f.path, fc.embedding_vector 
                    FROM files f 
                    JOIN file_content fc ON f.id = fc.file_id
                    WHERE fc.embedding_vector IS NOT NULL
                """)
                
                self.index = AnnoyIndex(self.dim, 'angular')
                self.file_id_map.clear()
                
                rows = cursor.fetchall()
                if not rows:
                    logging.warning("No embeddings found in database")
                    return

                for idx, row in enumerate(rows):
                    try:
                        embedding = np.frombuffer(row['embedding_vector'], dtype=np.float32)
                        if len(embedding) == self.dim:  # Verify embedding dimension
                            self.index.add_item(idx, embedding)
                            self.file_id_map[idx] = {
                                "id": row['id'],
                                "path": str(row['path'])
                            }
                    except Exception as e:
                        logging.error(f"Error loading embedding for file {row['path']}: {e}")
                        continue

                if len(self.file_id_map) > 0:
                    self.index.build(10)
                    logging.info(f"Successfully loaded {len(self.file_id_map)} embeddings")
                else:
                    logging.warning("No valid embeddings could be loaded")

        except Exception as e:
            logging.error(f"Failed to load embeddings: {e}", exc_info=True)
            self.file_id_map.clear()

    async def store_embedding(self, file_id: int, text: str, max_retries: int = 5) -> bool:
        """Store embedding with retry logic."""
        if not text.strip():
            logging.warning(f"Empty text for file_id {file_id}, skipping embedding")
            return False

        try:
            embedding = self.compute_embedding(text)
            if len(embedding) != self.dim:
                logging.error(f"Invalid embedding dimension for file_id {file_id}")
                return False

            for attempt in range(max_retries):
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO file_content (file_id, content_preview, embedding_vector)
                            VALUES (?, ?, ?)
                        """, (file_id, text[:1000], embedding.tobytes()))
                        
                    # Reload embeddings after successful storage
                    self._load_embeddings()
                    logging.info(f"Successfully stored and indexed embedding for file_id {file_id}")
                    return True

                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        wait_time = 0.3 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                        continue
                    raise

        except Exception as e:
            logging.error(f"Error storing embedding for file_id {file_id}: {e}", exc_info=True)
            return False

    def compute_embedding(self, text: str) -> np.ndarray:
        """Compute embedding for text."""
        return self.model.encode(text, show_progress_bar=False)
    
    async def _get_recency_score(self, file_path: str) -> float:
        """Compute recency score (0-1) using both modification and access times."""
        try:
            with get_db() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get both modification time and last access time
                cursor.execute("""
                    SELECT f.last_modified, fa.last_accessed
                    FROM files f
                    LEFT JOIN file_activity fa ON f.id = fa.file_id
                    WHERE f.path = ?
                """, (str(file_path),))
                
                result = cursor.fetchone()
                if not result:
                    return 0.0
                
                now = datetime.now()
                
                # Calculate modification recency score
                try:
                    last_modified = datetime.fromisoformat(result['last_modified'])
                    days_since_modified = (now - last_modified).days
                    modification_score = max(0.0, min(1.0, math.exp(-days_since_modified / 30)))
                except (TypeError, ValueError):
                    modification_score = 0.0
                
                # Calculate access recency score
                access_score = 0.0
                if result['last_accessed']:
                    try:
                        last_accessed = datetime.fromisoformat(result['last_accessed'])
                        days_since_accessed = (now - last_accessed).days
                        # Faster decay for access (15-day half-life vs 30-day for modification)
                        access_score = max(0.0, min(1.0, math.exp(-days_since_accessed / 15)))
                    except (TypeError, ValueError):
                        access_score = 0.0
                
                # Combine scores: give more weight to recent access (60%) than modification (40%)
                # Recent access reflects current user interest
                # Recent modification reflects content freshness
                combined_score = (0.4 * modification_score) + (0.6 * access_score)
                
                logging.debug(
                    f"Recency for {file_path}: "
                    f"modification={modification_score:.3f}, "
                    f"access={access_score:.3f}, "
                    f"combined={combined_score:.3f}"
                )
                
                return combined_score
                
        except Exception as e:
            logging.error(f"Error computing recency score for {file_path}: {e}", exc_info=True)
            return 0.0

    async def _get_cooccurrence_score(self, query_path: str, candidate_path: str) -> float:
        """Compute co-occurrence score (0-1) based on file access patterns."""
        try:
            with get_db() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get file IDs
                cursor.execute("SELECT id FROM files WHERE path = ?", (str(query_path),))
                query_result = cursor.fetchone()
                
                cursor.execute("SELECT id FROM files WHERE path = ?", (str(candidate_path),))
                candidate_result = cursor.fetchone()
                
                if not query_result or not candidate_result:
                    logging.warning(f"File not found in database")
                    return -1.0  # No co-occurrence possible if files not in DB
                
                query_id = query_result[0]
                candidate_id = candidate_result[0]
                
                # Check if activity_logs table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='file_cooccurrence'
                """)
                if not cursor.fetchone():
                    logging.debug("file_cooccurrence table does not exist")
                    return -1.0  # No co-occurrence data available
                
                # Query actual co-occurrence count
                cursor.execute("""
                    SELECT co_count FROM file_cooccurrence
                    WHERE (file_id_1 = ? AND file_id_2 = ?)
                       OR (file_id_1 = ? AND file_id_2 = ?)
                """, (query_id, candidate_id, candidate_id, query_id))
                
                result = cursor.fetchone()
                
                # If no co-occurrence found, return negative score
                if not result or result[0] is None:
                    logging.debug(f"No co-occurrence between {query_path} and {candidate_path}")
                    return -1.0  # Never accessed together
                
                cooccur = result[0]
                
                # Normalize using sigmoid function
                cooccurrence_score = 2 / (1 + math.exp(-cooccur / 5)) - 1
                
                logging.debug(
                    f"Co-occurrence for ({query_path}, {candidate_path}): "
                    f"co_count={cooccur}, score={cooccurrence_score:.3f}"
                )
                
                return cooccurrence_score
                
        except Exception as e:
            logging.error(f"Error computing co-occurrence score: {e}", exc_info=True)
            return -1.0

    async def recommend_similar(self, query_path: str, limit: int = 5) -> List[Dict]:
        """Find similar files using weighted multi-factor ranking."""
        try:
            # try to extract text from file on disk first
            query_text = extract_text_snippet(Path(query_path))
            if not query_text:
                # fallback: try to read stored preview from database
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT fc.content_preview
                            FROM files f
                            JOIN file_content fc ON f.id = fc.file_id
                            WHERE f.path = ?
                        """, (str(query_path),))
                        row = cursor.fetchone()
                        if row:
                            # accommodate sqlite returning tuple or Row
                            preview = row[0] if isinstance(row, (tuple, list)) else row['content_preview'] if hasattr(row, '__getitem__') else None
                            if preview:
                                query_text = preview
                                logging.info(f"Using stored content_preview for {query_path}")
                except Exception as e:
                    logging.warning(f"DB preview lookup failed for {query_path}: {e}")

            if not query_text:
                logging.warning(f"No text content available for {query_path}")
                return []

            # Get ranking weights from config or use defaults
            alpha = self.config.get("ranking", {}).get("alpha", 1.0)
            beta = self.config.get("ranking", {}).get("beta", 0.0)
            gamma = self.config.get("ranking", {}).get("gamma", 0.0)
            
            total = alpha + beta + gamma
            alpha, beta, gamma = map(lambda x: x/total, [alpha, beta, gamma])
            
            logging.info(f"Using ranking weights: semantic={alpha:.2f}, recency={beta:.2f}, cooccurrence={gamma:.2f}")

            query_embedding = self.compute_embedding(query_text)
            results = []

            with get_db() as conn:
                conn.row_factory = sqlite3.Row  # Enable dictionary-like access
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT f.path, fc.embedding_vector 
                    FROM files f 
                    JOIN file_content fc ON f.id = fc.file_id
                    WHERE f.path != ?
                """, (str(query_path),))
                
                rows = cursor.fetchall()
                for row in rows:
                    embedding_vector = row['embedding_vector']
                    if not embedding_vector:
                        continue
                        
                    path = str(row['path'])
                    stored_embedding = np.frombuffer(embedding_vector, dtype=np.float32)
                    
                    # Compute individual scores
                    similarity = float(1 - np.linalg.norm(query_embedding - stored_embedding))
                    recency = await self._get_recency_score(path)
                    cooccurrence = await self._get_cooccurrence_score(query_path, path)
                    
                    # Compute final score
                    final_score = (alpha * similarity + 
                                 beta * recency + 
                                 gamma * cooccurrence)
                    
                    results.append({
                        "path": path,
                        "final_score": round(final_score, 3),
                        "factors": {
                            "semantic_similarity": round(similarity, 3),
                            "recency": round(recency, 3),
                            "cooccurrence": round(cooccurrence, 3)
                        },
                        "weights": {
                            "semantic": round(alpha, 2),
                            "recency": round(beta, 2),
                            "cooccurrence": round(gamma, 2)
                        }
                    })

            # Sort by final score
            results.sort(key=lambda x: x["final_score"], reverse=True)
            logging.info(f"Found {len(results)} recommendations for {query_path}")
            return results[:limit]

        except Exception as e:
            logging.error(f"Error getting recommendations: {e}", exc_info=True)
            return []

    def _get_similarity_reason(self, similarity: float) -> str:
        """Get human-readable similarity description."""
        if similarity > 0.8:
            return "Very similar content"
        elif similarity > 0.6:
            return "Moderately similar content"
        return "Somewhat related content"
