"""Ensure spaCy model is downloaded at runtime if missing."""
import sys
import subprocess
from config.logging import get_logger

logger = get_logger(__name__)


def ensure_spacy_model(model_name: str = "en_core_web_sm"):
    """
    Download spaCy model if not already installed.
    
    This is a fallback for Docker builds where the model download might fail.
    """
    try:
        import spacy
        # Try to load the model
        spacy.load(model_name)
        logger.info(f"spaCy model '{model_name}' already installed")
    except OSError:
        # Model not found, download it
        logger.warning(f"spaCy model '{model_name}' not found, downloading...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "spacy", "download", model_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Successfully downloaded spaCy model '{model_name}'")
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Failed to download spaCy model '{model_name}': {e}",
                exc_info=True,
            )
            logger.warning("Entity extraction will be disabled")
