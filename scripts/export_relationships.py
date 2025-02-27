#!/usr/bin/env python3
import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to Python path to allow imports from src
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from neo4j import GraphDatabase

from src.config import Config

logger = logging.getLogger(__name__)


class RelationshipExporter:
    def __init__(self):
        """Initialize exporter with database connection."""
        store_config = (
            Config._load_config()
            .get("document_stores", {})
            .get("memgraph", {})
            .get("settings", {})
        )

        self.driver = GraphDatabase.driver(
            store_config.get("uri", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_URI")),
            auth=(
                store_config.get("user", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_USER")),
                store_config.get(
                    "password", Config.REQUIRED_ENV_VARS.get("MEMGRAPH_PASSWORD")
                ),
            ),
        )

    def get_entities(self) -> List[Dict]:
        """Get all entities and their associated note IDs."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Entity)
                OPTIONAL MATCH (n:Note)-[:CONTAINS]->(e)
                RETURN e.name as entity_name, collect(n.id) as note_ids
            """
            )
            return [dict(record) for record in result]

    def get_relationships(self) -> List[Dict]:
        """Get all relationships with their source notes."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (s:Entity)-[r:RELATION]->(o:Entity)
                MATCH (n:Note {id: r.note_id})
                RETURN s.name as subject, r.type as relationship, o.name as object,
                       n.id as note_id, n.title as note_title
            """
            )
            return [dict(record) for record in result]

    def write_csv(self, data: List[Dict], filename: str, fieldnames: List[str]) -> None:
        """Write data to CSV file."""
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Wrote {len(data)} rows to {filename}")

    def process_entities(self, entities: List[Dict]) -> List[Dict]:
        """Process entity data for CSV export."""
        return [
            {
                "entity_name": entity["entity_name"],
                "mentioned_in_notes": (
                    ",".join(entity["note_ids"]) if entity["note_ids"] else ""
                ),
            }
            for entity in entities
        ]

    def export(self, output_dir: str = ".") -> Tuple[str, str]:
        """Export entities and relationships to CSV files.

        Args:
            output_dir: Directory to write CSV files to

        Returns:
            Tuple of (entities_file_path, relationships_file_path)
        """
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Get data
            entities = self.get_entities()
            relationships = self.get_relationships()

            # Define output paths
            entities_path = os.path.join(output_dir, "entities.csv")
            relationships_path = os.path.join(output_dir, "relationships.csv")

            # Write entities CSV
            processed_entities = self.process_entities(entities)
            self.write_csv(
                processed_entities, entities_path, ["entity_name", "mentioned_in_notes"]
            )

            # Write relationships CSV
            self.write_csv(
                relationships,
                relationships_path,
                ["subject", "relationship", "object", "note_id", "note_title"],
            )

            return entities_path, relationships_path

        except Exception as e:
            logger.error(f"Failed to export data: {str(e)}")
            raise
        finally:
            self.driver.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Export entities and relationships from Memgraph to CSV files."
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write CSV files to (default: current directory)",
    )
    return parser.parse_args()


def main():
    """Main entry point for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    args = parse_args()

    try:
        exporter = RelationshipExporter()
        entities_file, relationships_file = exporter.export(args.output_dir)
        print(f"\nExport complete!")
        print(f"Entities file: {entities_file}")
        print(f"Relationships file: {relationships_file}")
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        exit(1)


if __name__ == "__main__":
    main()
