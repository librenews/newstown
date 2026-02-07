"""Download embedding models for Docker caching."""
import os
import torch
from sentence_transformers import SentenceTransformer

# Models to pre-download
MODELS = [
    "BAAI/bge-small-en-v1.5",
    # "BAAI/bge-large-en-v1.5",  # Uncomment if we want to cache the large model too
]

def download_models():
    """Download and cache models."""
    print(f"Downloading models to cache...")
    
    # Set cache dir to standard location if not set
    # SentenceTransformers uses TORCH_HOME or ~/.cache/torch/sentence_transformers
    
    for model_name in MODELS:
        print(f"Downloading {model_name}...")
        try:
            SentenceTransformer(model_name)
            print(f"Successfully downloaded {model_name}")
        except Exception as e:
            print(f"Failed to download {model_name}: {e}")
            # Don't fail the build, as we can download at runtime
            pass

if __name__ == "__main__":
    download_models()
