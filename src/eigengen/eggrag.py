import sqlite3
import sqlite_vec
import struct
import hashlib # Import hashlib for checksum calculation
from typing import List, Tuple

from eigengen import providers, operations, prompts
from eigengen.embeddings import CodeEmbeddings


def serialize_f32(vector: List[float]) -> bytes:
    """Serializes a list of floats into a compact binary format."""
    return struct.pack(f"{len(vector)}f", *vector)


def get_summary(model: providers.Model, content: str) -> str:
    """
    Generates a summary of the content using the specified model.

    Args:
        model (providers.Model): The model to use for summarization.
        content (str): The content to summarize.

    Returns:
        str: The summary of the content.
    """
    messages = [{"role": "user", "content": content}]
    chunks = operations.process_request(model, messages, prompts.get_prompt("summarize"))
    return "".join(chunks)


class EggRag:
    def __init__(self, model: providers.Model, db_path: str, embedding_dim: int, embeddings_provider: CodeEmbeddings):
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
        self.model = model

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
                content_hash TEXT, -- Add content_hash column
                content TEXT
            )
            """
        )
        # The virtual table to store embeddings.
        cur.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS egg_rag_embeddings
            USING vec0(metaid INTEGER, path TEXT, embedding float[{self.embedding_dim}])
            """
        )
        self.db.commit()

    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        """
        Computes the embedding of the file content and stores metadata and embedding in the database.
        Only updates if the file content has changed since last indexing.

        Args:
            file_path (str): The file path.
            modification_time (int): Modification time (e.g. Unix timestamp).
            content (str): File content.
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest() # Calculate content hash
        cur = self.db.cursor()

        # Check if the file is already indexed and if the content hash is the same
        cur.execute("SELECT id, content_hash FROM egg_rag_meta WHERE file_path = ?", (file_path,))
        row = cur.fetchone()
        if row:
            existing_id, existing_hash = row
            if existing_hash == content_hash:
                print(f"Content of '{file_path}' has not changed. Skipping indexing.")
                return # Skip indexing if content is the same
            else:
                print(f"Content of '{file_path}' has changed. Re-indexing.")
                cur.execute("DELETE FROM egg_rag_meta WHERE id = ?", (existing_id,))
                cur.execute("DELETE FROM egg_rag_embeddings WHERE rowid = ?", (existing_id,))


        # Compute embedding
        summary = get_summary(self.model, content)
        embedding_tensors = self.embeddings_provider.generate_embeddings(summary, kind="passage")
        # we have now a tensor of shape (chunks, embedding_dim)
        # we will use each chunk embedding to reference the same file in the metadata table
        # and store the embedding in the virtual table

        # create a list of serialized embeddings
        serialized_embeddings = []
        for index in range(len(embedding_tensors)):
            vector = embedding_tensors[index][0].tolist()
            serialized_embedding = serialize_f32(vector)
            serialized_embeddings.append(serialized_embedding)

        # Insert metadata and get the rowid.
        cur.execute(
            """
            INSERT INTO egg_rag_meta (file_path, modification_time, content_hash, content)
            VALUES (?, ?, ?, ?)
            """,
            (file_path, modification_time, content_hash, content), # Include content_hash
        )
        meta_id = cur.lastrowid
        # Insert embeddings with same rowid.
        cur.executemany(
            "INSERT INTO egg_rag_embeddings (metaid, path, embedding) VALUES (?, ?, ?)",
            [(meta_id, file_path, serialized_embedding) for serialized_embedding in serialized_embeddings],
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
        embedding_tensor = self.embeddings_provider.generate_embeddings(query_content, kind="query")
        query_embedding = embedding_tensor[0][0].tolist()
        serialized_query = serialize_f32(query_embedding)

        # first extract the rowids of the top N matches
        vector_query_sql = """
            SELECT metaid, vec_distance_cosine(embedding, ?) as distance FROM egg_rag_embeddings
            WHERE path like ?
            ORDER BY distance ASC
            LIMIT ?
        """
        active_prefix = path_prefix if path_prefix else ""
        cur = self.db.execute(
            vector_query_sql, (serialized_query, f"{active_prefix}%", top_n)
        )

        metaids = cur.fetchall()
        if not metaids:
            return []
        # get unique rowids
        rowids = list(set(metaids))

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
