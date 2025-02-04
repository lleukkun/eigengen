from dataclasses import dataclass
import torch
from sentence_transformers import SentenceTransformer


@dataclass
class CodeEmbeddingInput:
    texts: list[str]
    model_path: str = "Salesforce/SFR-Embedding-Code-2B_R"
    max_length: int = 32768

class CodeEmbeddings:
    def __init__(self, model_path: str = "Salesforce/SFR-Embedding-Code-2B_R", max_length: int = 32768):
        self.model_path = model_path
        self.model = SentenceTransformer(
            "Salesforce/SFR-Embedding-Code-2B_R", trust_remote_code=True
        )

        self.max_length = max_length


    def generate_query_embeddings(self, query: str) -> torch.Tensor:
        """Generate embeddings from a query"""
        query_instruction_example = (
            "Instruct: Given Code or Text, retrieval relevant content\nQuery: "
        )

        query_embeddings = self.model.encode(
            [query], prompt=query_instruction_example
        )

        return query_embeddings

    def generate_embeddings(self, passage: str) -> torch.Tensor:
        """Generate embeddings from tokenized input"""
        embeddings = self.model.encode([passage])
        return embeddings

    @classmethod
    def compute_similarity_scores(
        self,
        embeddings_a: torch.Tensor,
        embeddings_b: torch.Tensor
    ) -> torch.Tensor:
        """Compute similarity scores between two sets of embeddings"""
        return (embeddings_a @ embeddings_b.T) * 100

    def __repr__(self):
        return f"CodeEmbeddings(model_path={self.model_path})"

