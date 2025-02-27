"""Language model integration and relationship extraction module."""

from .extractor import RelationshipExtractor
from .provider import get_llm

__all__ = ["get_llm", "RelationshipExtractor"]
