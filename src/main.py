import argparse
import sys

from .sync import NotionSync
from .utils.logging import setup_logging


def main() -> None:
    """Main entry point for Notion sync application."""
    parser = argparse.ArgumentParser(description="Notion to Chroma/Neo4j sync script")
    parser.add_argument(
        "--clear-database",
        action="store_true",
        help="Clear the databases before running the script",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level",
    )

    args = parser.parse_args()
    setup_logging("logging.yaml", args.log_level)

    sync = NotionSync()

    if args.clear_database:
        sync.clear_databases()
        sys.exit()

    sync.sync()


if __name__ == "__main__":
    main()
