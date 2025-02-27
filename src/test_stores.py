import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.storage.store_manager import StoreManager

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def compare_stores():
    """Compare content between Chroma and Memgraph stores."""
    manager = StoreManager()

    # Get a test document from each store
    for notion_id in [
        "56fc9399-a462-492c-8d7b-19453c95b7a5"
    ]:  # Test Critical Alert doc
        logger.info(f"\nComparing document {notion_id}:")

        # Get from Chroma
        chroma_store = manager.get_store("chroma")
        if chroma_store:
            logger.info("\nChroma content:")
            for doc in chroma_store.get_documents(notion_id):
                logger.info(f"Title: {doc['title']}")
                logger.info(f"Content:\n{doc['content']}")
                logger.info("Newlines count: %d", doc["content"].count("\n"))
                logger.info(f"Content bytes: {doc['content'].encode()}")

        # Get from Memgraph
        memgraph_store = manager.get_store("memgraph")
        if memgraph_store:
            logger.info("\nMemgraph content:")
            for doc in memgraph_store.get_documents(notion_id):
                logger.info(f"Title: {doc['title']}")
                logger.info(f"Content:\n{doc['content']}")
                logger.info("Newlines count: %d", doc["content"].count("\n"))
                logger.info(f"Content bytes: {doc['content'].encode()}")

    manager.close()


if __name__ == "__main__":
    compare_stores()
