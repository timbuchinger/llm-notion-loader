#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Add parent directory to Python path to allow imports from src
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from src.config import Config
from src.storage.pinecone import PineconeStore

logger = logging.getLogger(__name__)


def confirm_deletion(namespace: str, notion_id: Optional[str] = None) -> bool:
    """Prompt for confirmation before deletion."""
    if notion_id:
        message = f"Are you sure you want to delete document {notion_id} from namespace '{namespace}'? [y/N] "
    else:
        message = f"Are you sure you want to delete ALL documents from namespace '{namespace}'? [y/N] "

    response = input(message)
    return response.lower() == "y"


def verify_namespace_empty(
    store: PineconeStore, max_retries: int = 5, verification_delay: float = 2.0
) -> bool:
    """Verify namespace is empty with retries and exponential backoff.

    Args:
        store: PineconeStore instance
        max_retries: Maximum number of verification attempts
        verification_delay: Initial delay before first verification attempt

    Returns:
        True if namespace is confirmed empty, False if vectors still exist
    """
    base_delay = verification_delay

    # Initial delay for eventual consistency
    logger.debug(f"Waiting {verification_delay}s before verification...")
    time.sleep(verification_delay)

    for attempt in range(max_retries):
        # Query for any remaining vectors
        verification = store.index.query(
            vector=[0] * 768,
            filter={},
            top_k=1,
            include_metadata=True,
            namespace=store.namespace,
        )

        if not verification.matches:
            if attempt > 0:
                logger.debug(f"Namespace confirmed empty on attempt {attempt + 1}")
            return True

        # If vectors found, wait with exponential backoff
        delay = base_delay * (2**attempt)
        logger.debug(
            f"Vectors still present on attempt {attempt + 1}, "
            f"waiting {delay}s before retry"
        )
        time.sleep(delay)

    return False


def delete_namespace(
    namespace: Optional[str] = None,
    notion_id: Optional[str] = None,
    force: bool = False,
    verification_delay: float = 2.0,
) -> None:
    """Delete documents from a Pinecone namespace.

    Args:
        namespace: Optional namespace override
        notion_id: Optional specific document ID to delete
        force: Skip confirmation prompt if True
        verification_delay: Seconds to wait before verifying deletion
    """
    try:
        # Initialize store with optional namespace override
        config = Config._load_config()
        if namespace:
            # Override namespace in config
            if "document_stores" not in config:
                config["document_stores"] = {}
            if "pinecone" not in config["document_stores"]:
                config["document_stores"]["pinecone"] = {}
            if "settings" not in config["document_stores"]["pinecone"]:
                config["document_stores"]["pinecone"]["settings"] = {}
            config["document_stores"]["pinecone"]["settings"]["namespace"] = namespace

        store = PineconeStore(config)

        # Get effective namespace
        effective_namespace = namespace or store.namespace
        logger.info(f"Using namespace: {effective_namespace}")

        # Confirm deletion unless forced
        if not force and not confirm_deletion(effective_namespace, notion_id):
            logger.info("Deletion cancelled")
            return

        if notion_id:
            # Delete specific document
            logger.info(f"Deleting document {notion_id}...")
            store.clean_document(notion_id)
            logger.info(f"Successfully deleted document {notion_id}")
        else:
            # Delete all documents in namespace
            logger.info("Fetching documents to delete...")
            try:
                # Query for all document IDs in namespace
                response = store.index.query(
                    vector=[0] * 768,  # Dummy vector to get IDs
                    filter={},
                    top_k=10000,
                    include_metadata=True,
                    namespace=store.namespace,
                )

                if not response.matches:
                    logger.info("No documents found in namespace")
                    return

                # Delete all vectors in batches
                batch_size = 100
                total_deleted = 0

                for i in range(0, len(response.matches), batch_size):
                    batch = response.matches[i : i + batch_size]
                    ids_to_delete = [match.id for match in batch]

                    logger.debug(f"Deleting batch of {len(ids_to_delete)} vectors...")
                    store.index.delete(ids=ids_to_delete, namespace=store.namespace)
                    total_deleted += len(ids_to_delete)

                logger.info(
                    f"Successfully deleted {total_deleted} vectors from namespace {effective_namespace}"
                )

                # Verify namespace is empty with retries
                if not verify_namespace_empty(
                    store, verification_delay=verification_delay
                ):
                    logger.warning(
                        "Some vectors may remain in namespace - try running the script again"
                    )

            except Exception as e:
                logger.error(f"Failed to delete vectors: {str(e)}", exc_info=True)
                raise

    except Exception as e:
        logger.error(f"Failed to delete from namespace: {str(e)}", exc_info=True)
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Delete documents from a Pinecone namespace"
    )
    parser.add_argument(
        "--namespace",
        help="Override the namespace configured in document_stores.yaml",
    )
    parser.add_argument(
        "--notion-id",
        help="Delete only the specified Notion document",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--verification-delay",
        type=float,
        default=2.0,
        help="Seconds to wait before verifying deletion (default: 2.0)",
    )
    return parser.parse_args()


def main():
    """Main entry point for the script."""
    args = parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        delete_namespace(
            namespace=args.namespace,
            notion_id=args.notion_id,
            force=args.force,
            verification_delay=args.verification_delay,
        )
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
