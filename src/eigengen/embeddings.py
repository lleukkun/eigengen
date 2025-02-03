from dataclasses import dataclass
import torch
import torch.nn.functional as F
from transformers import AutoModel


@dataclass
class CodeEmbeddingInput:
    texts: list[str]
    model_path: str = "Salesforce/SFR-Embedding-Code-2B_R"
    max_length: int = 32768

class CodeEmbeddings:
    def __init__(self, model_path: str = "Salesforce/SFR-Embedding-Code-2B_R", max_length: int = 32768):
        self.model_path = model_path
        self.model = AutoModel.from_pretrained(
            self.model_path,
            trust_remote_code=True
        )
        self.max_length = max_length


    def generate_query_embeddings(self, query: str) -> torch.Tensor:
        """Generate embeddings from a query"""
        query_instruction_example = "Given Code or Text, retrieval relevant content"
        query_embeddings = self.model.encode_queries(
            [query], instruction=query_instruction_example, max_length=self.max_length
        )
        normalized = F.normalize(query_embeddings)

        return normalized

    def generate_embeddings(self, passage: str) -> torch.Tensor:
        """Generate embeddings from tokenized input"""
        normalized = F.normalize(self.model.encode_corpus([passage], max_length=self.max_length))
        return normalized

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

