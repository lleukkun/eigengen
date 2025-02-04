from dataclasses import dataclass
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel


@dataclass
class CodeEmbeddingInput:
    texts: list[str]
    model_path: str = "intfloat/multilingual-e5-large"
    max_length: int = 512



def average_pool(last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]


class CodeEmbeddings:
    def __init__(
        self,
        model_path: str = "intfloat/multilingual-e5-large",
        max_length: int = 32768,
    ):
        self.model_path = model_path
        self.model = AutoModel.from_pretrained(model_path, trust_remote_code=True)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=True
        )

        self.max_length = max_length


    def generate_embeddings(self, input_text: str, kind: str = "passage") -> list[torch.Tensor]:
        """Generate embeddings from tokenized input"""
        # tokenize the input
        batch_dict = self.tokenizer([f"{kind}: {input_text}"], return_tensors="pt", max_length=128000, truncation=True)
        # reshape the batch_dict token tensor so that we get 512 token sub-passages
        # we will use these sub-passages to encode the embeddings
        max_tokens = 512
        overlap = 0.25
        stride = int(max_tokens * (1 - overlap))
        token_chunks = []
        i = 0
        embeddings = []
        while i < (batch_dict["input_ids"].shape[1]):
            # Always slice exactly max_tokens or fewer tokens from the list
            chunk = batch_dict["input_ids"][:, i:i + max_tokens]
            token_chunks.append(chunk)
            i += stride

        for idx, chunk in enumerate(token_chunks):
            # Convert chunk to a PyTorch tensor and add batch dimension
            input_ids = chunk
            # Create an attention mask of 1s (or compute it appropriately)
            attention_mask = torch.ones_like(input_ids)

            # Feed directly into the model
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            # normalize
            embeddings.append(F.normalize(average_pool(outputs.last_hidden_state, attention_mask), p=2, dim=1))

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

