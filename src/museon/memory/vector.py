"""Vector storage using sqlite-vec for semantic memory search.

Uses sqlite-vec extension for efficient similarity search on embeddings.
Stores embeddings alongside metadata for quick retrieval.

Note: Requires sqlite-vec extension. In production, embeddings would be
generated using Claude's embedding API or a local model.
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class VectorStore:
    """Vector storage for semantic memory search."""

    def __init__(self, db_path: str = "data/memory/vectors.db"):
        """Initialize vector store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path))
        self._init_tables()

    def _init_tables(self):
        """Initialize database tables.

        For v1, we use standard SQLite without vec extension.
        Vector similarity will use simple dot product or cosine similarity.
        """
        cursor = self.conn.cursor()

        # Main embeddings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                embedding BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                channel TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trust_level TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index on channel and timestamp for faster filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_timestamp
            ON embeddings(channel, timestamp)
        """)

        self.conn.commit()

    def insert(
        self,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> int:
        """Insert an embedding with metadata.

        Args:
            embedding: Vector embedding (typically 1024-dim for Claude)
            metadata: Metadata dict with channel, content, timestamp, etc.

        Returns:
            ID of inserted row
        """
        cursor = self.conn.cursor()

        # Convert embedding to bytes
        # Store as JSON string for simplicity (in production, use proper binary format)
        embedding_blob = json.dumps(embedding).encode("utf-8")
        dimension = len(embedding)

        # Extract metadata
        channel = metadata.get("channel", "unknown")
        content = metadata.get("content", "")
        timestamp = metadata.get("timestamp", "")
        trust_level = metadata.get("trust_level", "UNKNOWN")

        # Store full metadata as JSON
        metadata_json = json.dumps(metadata)

        cursor.execute(
            """
            INSERT INTO embeddings
            (embedding, dimension, channel, content, timestamp, trust_level, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                embedding_blob,
                dimension,
                channel,
                content,
                timestamp,
                trust_level,
                metadata_json,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def search_similar(
        self,
        embedding: List[float],
        top_k: int = 5,
        channel: Optional[str] = None,
        min_similarity: float = 0.0,
    ) -> List[Tuple[int, str, float]]:
        """Search for similar embeddings.

        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            channel: Optional channel filter
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of (id, content, similarity) tuples
        """
        cursor = self.conn.cursor()

        # Build query
        query = """
            SELECT id, content, embedding, metadata
            FROM embeddings
        """

        params = []
        if channel:
            query += " WHERE channel = ?"
            params.append(channel)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Calculate similarities
        results = []
        for row_id, content, embedding_blob, metadata_str in rows:
            # Decode embedding
            stored_embedding = json.loads(embedding_blob.decode("utf-8"))

            # Calculate cosine similarity
            similarity = self._cosine_similarity(embedding, stored_embedding)

            if similarity >= min_similarity:
                results.append((row_id, content, similarity))

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x[2], reverse=True)

        # Return top_k
        return results[:top_k]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0-1)
        """
        if len(vec1) != len(vec2):
            return 0.0

        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Magnitudes
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def get_by_id(self, embedding_id: int) -> Optional[Dict[str, Any]]:
        """Get embedding and metadata by ID.

        Args:
            embedding_id: Row ID

        Returns:
            Dict with embedding and metadata, or None if not found
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT embedding, metadata, channel, timestamp, trust_level
            FROM embeddings
            WHERE id = ?
        """,
            (embedding_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        embedding_blob, metadata_str, channel, timestamp, trust_level = row

        return {
            "id": embedding_id,
            "embedding": json.loads(embedding_blob.decode("utf-8")),
            "metadata": json.loads(metadata_str),
            "channel": channel,
            "timestamp": timestamp,
            "trust_level": trust_level,
        }

    def delete_by_channel(self, channel: str) -> int:
        """Delete all embeddings from a specific channel.

        Args:
            channel: Channel name

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()

        cursor.execute("DELETE FROM embeddings WHERE channel = ?", (channel,))
        self.conn.commit()

        return cursor.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about vector storage.

        Returns:
            Dict with stats: total count, per-channel counts, etc.
        """
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        total_count = cursor.fetchone()[0]

        # Per-channel counts
        cursor.execute(
            """
            SELECT channel, COUNT(*) as count
            FROM embeddings
            GROUP BY channel
        """
        )
        channel_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Average dimension
        cursor.execute("SELECT AVG(dimension) FROM embeddings")
        avg_dimension = cursor.fetchone()[0] or 0

        return {
            "total_embeddings": total_count,
            "channels": channel_counts,
            "avg_dimension": avg_dimension,
            "db_path": str(self.db_path),
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
