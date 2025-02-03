import sqlite3
import sqlite_vec
import struct
from typing import List, Tuple

import torch
from eigengen.embeddings import CodeEmbeddings

def serialize_f32(vector: List[float]) -> bytes:
    """Serializes a list of floats into a compact binary format."""
    return struct.pack(f"{len(vector)}f", *vector)

class EggRag:
    def __init__(self, db_path: str, embedding_dim: int, embeddings_provider: CodeEmbeddings):
        """
        Initializes the EggRag semantic storage.

        Args:
            db_path (str): Path to the sqlite database. Use ":memory:" for in-memory DB.
            embedding_dim (int): Dimension of the vector embeddings.
            embeddings_provider (CodeEmbeddings): Instance for producing embeddings.
        """
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.embeddings_provider = embeddings_provider
        self.db = sqlite3.connect(self.db_path)
        # load sqlite_vec extension
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self._initialize_tables()

    def _initialize_tables(self):
        """
        Creates the metadata table and the virtual table (using sqlite_vec) for embeddings.
        """
        cur = self.db.cursor()
        # Metadata table to hold file details.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS egg_rag_meta (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                modification_time INTEGER,
                content TEXT
            )
            """
        )
        # The virtual table to store embeddings.
        cur.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS egg_rag_embeddings
            USING vec0(rowid INTEGER PRIMARY KEY, path TEXT, embedding float[{self.embedding_dim}])
            """
        )
        self.db.commit()

    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        """
        Computes the embedding of the file content and stores metadata and embedding in the database.

        Args:
            file_path (str): The file path.
            modification_time (int): Modification time (e.g. Unix timestamp).
            content (str): File content.
        """
        # Compute embedding
        embedding_tensor = self.embeddings_provider.generate_embeddings(content)
        embedding_list = embedding_tensor[0].tolist()
        serialized_embedding = serialize_f32(embedding_list)

        cur = self.db.cursor()

        # check if the file is already indexed and if yes, delete the previous entry
        cur.execute("SELECT id FROM egg_rag_meta WHERE file_path = ?", (file_path,))
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM egg_rag_meta WHERE id = ?", (row[0],))
            cur.execute("DELETE FROM egg_rag_embeddings WHERE rowid = ?", (row[0],))

        # Insert metadata and get the rowid.
        cur.execute(
            """
            INSERT INTO egg_rag_meta (file_path, modification_time, content)
            VALUES (?, ?, ?)
            """,
            (file_path, modification_time, content),
        )
        row_id = cur.lastrowid
        # Insert embedding with same rowid.
        cur.execute(
            "INSERT INTO egg_rag_embeddings (rowid, path, embedding) VALUES (?, ?, ?)",
            (row_id, file_path, serialized_embedding),
        )
        self.db.commit()

    def retrieve(self, query_content: str, top_n: int, path_prefix: str | None = None) -> List[Tuple[str, int, str]]:
        """
        Returns the top N best matches for the query content.

        Args:
            query_content (str): The query file content.
            top_n (int): Number of matches to return.

        Returns:
            List[Tuple[str, int, str, float]]: A list of tuples containing file_path, modification_time,
            content, and the computed distance from the query embedding.
        """
        # Compute embedding for the query.
        embedding_tensor = self.embeddings_provider.generate_query_embeddings(query_content)
        query_embedding = embedding_tensor[0].tolist()
        serialized_query = serialize_f32(query_embedding)

        # first extract the rowids of the top N matches
        vector_query_sql = """
            SELECT rowid, vec_distance_cosine(embedding, ?) as distance FROM egg_rag_embeddings
            WHERE path like ?
            ORDER BY distance ASC
            LIMIT ?
        """
        active_prefix = path_prefix if path_prefix else ""
        cur = self.db.execute(
            vector_query_sql, (serialized_query, f"{active_prefix}%", top_n)
        )

        rowids = cur.fetchall()
        if not rowids:
            return []
        # then fetch the metadata for the top N matches
        rowids_str = ", ".join(str(rowid) for rowid, _ in rowids)
        meta_query_sql = f"""
            SELECT file_path, modification_time, content
            FROM egg_rag_meta
            WHERE id IN ({rowids_str})
        """
        cur = self.db.execute(meta_query_sql)
        results = cur.fetchall()
        return results
