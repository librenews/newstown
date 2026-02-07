"""Entity extraction using spaCy."""
from typing import Optional
from dataclasses import dataclass
from config.logging import get_logger

logger = get_logger(__name__)

# Try to import spaCy - handle compatibility issues with Python 3.12
try:
    import spacy
    SPACY_AVAILABLE = True
except (ImportError, TypeError) as e:
    logger.warning(f"spaCy not available due to compatibility issue: {e}")
    logger.warning("Entity extraction will be disabled")
    SPACY_AVAILABLE = False
    spacy = None


@dataclass
class Entity:
    """Extracted entity."""
    text: str
    label_: str  # PERSON, ORG, GPE, etc.
    start: int
    end: int


class EntityExtractor:
    """Extract entities from text using spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize entity extractor.
        
        Args:
            model_name: spaCy model to use (must be downloaded)
        """
        # Try to download model at runtime if missing (for Docker)
        from ingestion.spacy_helper import ensure_spacy_model
        ensure_spacy_model(model_name)
        
        try:
            self.nlp = spacy.load(model_name)
            logger.info(f"Loaded spaCy model: {model_name}")
        except OSError:
            logger.error(
                f"spaCy model '{model_name}' not found. "
                f"Install with: python -m spacy download {model_name}"
            )
            self.nlp = None

    def extract(self, text: str) -> list[Entity]:
        """
        Extract entities from text.
        
        Args:
            text: Text to extract entities from
            
        Returns:
            List of extracted entities
        """
        if not self.nlp:
            logger.warning("spaCy model not loaded, returning empty entities")
            return []

        if not text or not text.strip():
            return []

        try:
            doc = self.nlp(text)

            entities = []
            for ent in doc.ents:
                # Filter for relevant entity types
                if ent.label_ in [
                    "PERSON",
                    "ORG",
                    "GPE",  # Geo-political entity (countries, cities)
                    "PRODUCT",
                    "LAW",
                    "EVENT",
                    "MONEY",
                    "PERCENT",
                ]:
                    entities.append(
                        Entity(
                            text=ent.text,
                            label_=ent.label_,
                            start=ent.start_char,
                            end=ent.end_char,
                        )
                    )

            logger.info(
                "Entities extracted",
                text_length=len(text),
                entity_count=len(entities),
            )

            return entities

        except Exception as e:
            logger.error("Entity extraction failed", error=str(e))
            return []

    def extract_by_type(self, text: str, entity_type: str) -> list[Entity]:
        """Extract only entities of a specific type."""
        all_entities = self.extract(text)
        return [e for e in all_entities if e.label_ == entity_type]

    def get_people(self, text: str) -> list[str]:
        """Extract person names from text."""
        entities = self.extract_by_type(text, "PERSON")
        return [e.text for e in entities]

    def get_organizations(self, text: str) -> list[str]:
        """Extract organization names from text."""
        entities = self.extract_by_type(text, "ORG")
        return [e.text for e in entities]

    def get_locations(self, text: str) -> list[str]:
        """Extract location names from text."""
        entities = self.extract_by_type(text, "GPE")
        return [e.text for e in entities]


# Global entity extractor instance
entity_extractor = EntityExtractor()
