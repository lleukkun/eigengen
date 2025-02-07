import sqlite3
import struct
import hashlib  # Import hashlib for checksum calculation
from typing import List, Tuple
import hnswlib   # New import for nearest neighbour search
import numpy as np
import time  # Added for retry delay

from eigengen import providers, operations, prompts
from eigengen.embeddings import CodeEmbeddings


def serialize_f32(vector: List[float]) -> bytes:
    """Serializes a list of floats into a compact binary format."""
    return struct.pack(f"{len(vector)}f", *vector)


def serialize_embedding_matrix(embeddings: List[List[float]]) -> bytes:
    """
    Serializes a list of embeddings (each a list of floats) into a single BLOB.
    Format:
      count(int32), embedding_dim(int32), followed by count*embedding_dim floats.
    """
    count = len(embeddings)
    if count == 0:
        return b""
    embedding_dim = len(embeddings[0])
    flat_list = [val for vec in embeddings for val in vec]
    fmt = f"ii{count * embedding_dim}f"
    return struct.pack(fmt, count, embedding_dim, *flat_list)


def deserialize_embedding_matrix(blob: bytes) -> List[List[float]]:
    """
    Deserializes a BLOB into a list of embeddings.
    """
    if not blob:
        return []
    # header: two integers (count and embedding_dim)
    count, embedding_dim = struct.unpack("ii", blob[:8])
    total_floats = count * embedding_dim
    floats = struct.unpack(f"{total_floats}f", blob[8:])
    return [list(floats[i*embedding_dim:(i+1)*embedding_dim]) for i in range(count)]


def get_summary(model: providers.Model, content: str) -> str:
    """
    Generates a summary of the content using the specified model,
    retrying up to 3 attempts in case of errors.

    Args:
        model (providers.Model): The model to use for summarization.
        content (str): The content to summarize.

    Returns:
        str: The summary of the content.

    Raises:
        Exception: The last exception encountered if all retries fail.
    """
    attempts = 3  # Total attempts: initial try + 2 retries
    for attempt in range(attempts):
        try:
            messages = [{"role": "user", "content": content}]
            chunks = operations.process_request(model, messages, prompts.get_prompt("summarize"))
            return "".join(chunks)
        except Exception as e:
            if attempt < attempts - 1:
                delay = 2 ** attempt  # exponential backoff
                print(f"Error generating summary (attempt {attempt + 1}/{attempts}): {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                raise e


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
        # No longer loading sqlite_vec extension.
        self._initialize_tables()
        self.model = model

    def _initialize_tables(self):
        """
        Creates a unified table to hold metadata and serialized embeddings.
        """
        cur = self.db.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS egg_rag (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                modification_time INTEGER,
                content_hash TEXT,
                content TEXT,
                embedding BLOB
            )
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
        content_hash = hashlib.sha256(content.encode()).hexdigest()  # Calculate content hash
        cur = self.db.cursor()

        # Check if the file is already indexed and if the content hash is the same
        cur.execute("SELECT id, content_hash FROM egg_rag WHERE file_path = ?", (file_path,))
        row = cur.fetchone()
        if row:
            existing_id, existing_hash = row
            if existing_hash == content_hash:
                print(f"Content of '{file_path}' has not changed. Skipping indexing.")
                return  # Skip indexing if content is the same
            else:
                print(f"Content of '{file_path}' has changed. Re-indexing.")
                cur.execute("DELETE FROM egg_rag WHERE id = ?", (existing_id,))

        # Compute embedding
        summary = get_summary(self.model, content)
        embedding_tensors = self.embeddings_provider.generate_embeddings(summary, kind="passage")
        # Collect all embeddings (each chunk) as a list of float lists
        embeddings_list = []
        for tensor in embedding_tensors:
            # tensor shape is (1, embedding_dim)
            vector = tensor[0].tolist()
            embeddings_list.append(vector)

        serialized_blob = serialize_embedding_matrix(embeddings_list)

        # Insert metadata along with the embedding BLOB.
        cur.execute(
            """
            INSERT INTO egg_rag (file_path, modification_time, content_hash, content, embedding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (file_path, modification_time, content_hash, content, serialized_blob),
        )

        self.db.commit()

    def retrieve(self, query_content: str, top_n: int, path_prefix: str | None = None) -> List[Tuple[str, int, str]]:
        """
        Returns the top N best matches for the query content using hnswlib for nearest neighbour search.

        Args:
            query_content (str): The query text.
            top_n (int): Number of unique file matches to return.
            path_prefix (str | None): Optional prefix to filter file_path.

        Returns:
            List[Tuple[str, int, str]]: A list of tuples containing file_path, modification_time, content.
        """
        # Compute embedding for the query.
        embedding_tensor = self.embeddings_provider.generate_embeddings(query_content, kind="query")
        query_embedding = embedding_tensor[0][0].tolist()
        query_np = np.array(query_embedding, dtype=np.float32)

        # Load all embeddings and related meta from the database
        cur = self.db.cursor()
        if path_prefix:
            cur.execute("SELECT id, embedding FROM egg_rag WHERE file_path LIKE ?", (f"{path_prefix}%",))
        else:
            cur.execute("SELECT id, embedding FROM egg_rag")
        rows = cur.fetchall()
        if not rows:
            return []

        # Prepare lists for hnswlib index. Each stored vector comes with its file id.
        stored_vectors = []
        file_ids = []
        for file_id, blob in rows:
            vectors = deserialize_embedding_matrix(blob)
            for vec in vectors:
                stored_vectors.append(vec)
                file_ids.append(file_id)

        if len(stored_vectors) == 0:
            return []

        data = np.array(stored_vectors, dtype=np.float32)

        # Build the HNSW index.
        num_elements = data.shape[0]
        # Using cosine distance (vectors are normalized in embeddings_generation)
        p = hnswlib.Index(space='cosine', dim=self.embedding_dim)
        p.init_index(max_elements=num_elements, ef_construction=200, M=16)
        p.add_items(data, np.array(range(num_elements)))
        p.set_ef(50)

        # Query the index. We request more than top_n in case multiple vectors map to the same file.
        k = min(num_elements, top_n * 2)
        labels, distances = p.knn_query(query_np, k=k)

        # Deduplicate: select best match per file.
        file_to_distance = {}
        for idx, dist in zip(labels[0], distances[0]):
            fid = file_ids[idx]
            if fid not in file_to_distance or dist < file_to_distance[fid]:
                file_to_distance[fid] = dist

        # Sort file_ids by best distance and take top_n
        sorted_file_ids = sorted(file_to_distance.items(), key=lambda x: x[1])[:top_n]
        final_ids = [fid for fid, _ in sorted_file_ids]

        # Fetch metadata for the chosen file ids.
        format_ids = ", ".join("?" for _ in final_ids)
        meta_query_sql = f"""
            SELECT file_path, modification_time, content
            FROM egg_rag
            WHERE id IN ({format_ids})
        """
        meta_cur = self.db.execute(meta_query_sql, final_ids)
        results = meta_cur.fetchall()
        return results

# NEW: No-Operation implementation when RAG is disabled.
class NoOpEggRag:
    def add_file(self, file_path: str, modification_time: int, content: str) -> None:
        print(f"RAG is disabled. Skipping indexing for '{file_path}'.")

    def retrieve(self, query_content: str, top_n: int, path_prefix: str | None = None) -> list[tuple[str, int, str]]:
        return []
