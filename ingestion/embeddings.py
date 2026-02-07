"""Embedding service using local sentence-transformers."""
import torch
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Generates vector embeddings for text using local models.
    
    Supports switching between development (small) and production (large) models
    via settings.embedding_model.
    """

    def __init__(self):
        """Initialize the embedding model."""
        self.model_name = settings.embedding_model
        self.model: Optional[SentenceTransformer] = None
        self._device = self._get_device()

    def _get_device(self) -> str:
        """Determine the best available device."""
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @property
    def dimension(self) -> int:
        """Return the embedding dimension based on the model."""
        if "small" in self.model_name:
            return 384
        elif "large" in self.model_name:
            return 1024
        elif "base" in self.model_name:
            return 768
        # Fallback for OpenAI or others
        return 1536

    def _load_model(self) -> None:
        """Lazy load the model to save resources on startup if not needed immediately."""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name} on {self._device}")
            try:
                self.model = SentenceTransformer(self.model_name, device=self._device)
                logger.info(f"Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load embedding model {self.model_name}: {e}")
                raise

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single string.
        
        Args:
            text: Input text
            
        Returns:
            List of floats representing the vector
        """
        if not text:
            return []
            
        self._load_model()
        if not self.model:
            return []

        # sentence-transformers returns numpy array, convert to list
        embedding = self.model.encode(text, convert_to_tensor=False)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of strings.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of vectors
        """
        if not texts:
            return []
            
        self._load_model()
        if not self.model:
            return []

        embeddings = self.model.encode(texts, convert_to_tensor=False)
        return embeddings.tolist()


# Global instance
embedding_service = EmbeddingService()
