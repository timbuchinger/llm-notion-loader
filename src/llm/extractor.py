import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from .provider import get_llm

logger = logging.getLogger(__name__)


class RelationshipExtractor:
    def __init__(self):
        self.llm = get_llm()

        # Load relationship extraction prompt
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "relationships.md"
        )
        with open(prompt_path) as f:
            self.prompt_template = f.read()

    def extract_relationships(self, text: str) -> List[Dict[str, str]]:
        """Extract relationships from text using LLM.

        Args:
            text: The text to extract relationships from.

        Returns:
            List of relationship dictionaries with 'subject', 'relationship', and 'object' fields.
        """
        prompt = self.prompt_template + f"\n\nText to analyze:\n{text}"

        response = self.llm.invoke(prompt)
        try:
            # Clean response content
            content = str(
                response.content if hasattr(response, "content") else response
            )

            # Remove thinking tags and content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

            # Remove markdown code blocks
            content = re.sub(r"```json\s*|\s*```", "", content)

            # Find first occurrence of [ and last occurrence of ]
            start = content.find("[")
            end = content.rfind("]")

            if start != -1 and end != -1:
                content = content[start : end + 1]

            logger.debug(f"Cleaned response content: {content}")

            # Parse JSON
            relationships = json.loads(content)
            logger.info(f"Relationships: {relationships}")

            return relationships

        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Raw response: {response}")
            return []

    def _validate_relationship(self, rel: Dict[str, str]) -> bool:
        """Validate a single relationship dictionary.

        Args:
            rel: Relationship dictionary with 'subject', 'relationship', and 'object' fields

        Returns:
            True if relationship is valid, False otherwise
        """
        # Check all required fields exist and are non-empty strings
        if not all(
            isinstance(rel.get(k, ""), str) and rel.get(k, "").strip()
            for k in ["subject", "relationship", "object"]
        ):
            logger.warning(
                f"Relationship missing required fields or has empty values: {rel}"
            )
            return False

        # Check field lengths (prevent extremely long values)
        MAX_LENGTH = 1000  # Maximum reasonable length for entity names
        for k in ["subject", "relationship", "object"]:
            if len(rel[k]) > MAX_LENGTH:
                logger.warning(
                    f"Relationship field '{k}' exceeds maximum length: {rel}"
                )
                return False

        return True

    def process_document(self, title: str, content: str) -> List[Dict[str, str]]:
        """Process a document to extract relationships.

        Args:
            title: The document title
            content: The document content

        Returns:
            List of validated extracted relationships
        """
        full_content = f"# {title}\n\n{content}"
        relationships = self.extract_relationships(full_content)

        # Filter out invalid relationships
        valid_relationships = [
            rel for rel in relationships if self._validate_relationship(rel)
        ]

        if len(relationships) != len(valid_relationships):
            logger.warning(
                f"Filtered out {len(relationships) - len(valid_relationships)} invalid relationships"
            )

        return valid_relationships
