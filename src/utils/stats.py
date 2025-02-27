"""Statistics tracking utilities."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock


@dataclass
class SyncStats:
    """Statistics for sync operations."""

    # Runtime state (not reset between runs)
    start_time: float = field(default_factory=time.time)
    end_time: float = field(default=None)

    # Document statistics
    total_documents: int = field(default=0)
    documents_processed: int = field(default=0)
    documents_skipped: int = field(default=0)
    documents_errored: int = field(default=0)

    # Database operations (per store)
    chroma_insertions: int = field(default=0)
    chroma_updates: int = field(default=0)
    chroma_deletions: int = field(default=0)
    memgraph_nodes_created: int = field(default=0)
    memgraph_relationships_created: int = field(default=0)
    memgraph_deletions: int = field(default=0)

    # Chunking statistics
    llm_chunked_docs: int = field(default=0)
    token_chunked_docs: int = field(default=0)
    llm_chunks_created: int = field(default=0)
    token_chunks_created: int = field(default=0)

    # Rate limiting statistics
    rate_limit_hits: int = field(default=0)
    rate_limit_wait_time: float = field(default=0.0)

    def __post_init__(self):
        """Initialize thread safety lock."""
        self._lock = Lock()

    def reset(self):
        """Reset all counters to initial state."""
        with self._lock:
            self.documents_processed = 0
            self.documents_skipped = 0
            self.documents_errored = 0
            self.chroma_insertions = 0
            self.chroma_updates = 0
            self.chroma_deletions = 0
            self.memgraph_nodes_created = 0
            self.memgraph_relationships_created = 0
            self.memgraph_deletions = 0
            self.llm_chunked_docs = 0
            self.token_chunked_docs = 0
            self.llm_chunks_created = 0
            self.token_chunks_created = 0
            self.rate_limit_hits = 0
            self.rate_limit_wait_time = 0.0
            self.start_time = time.time()
            self.end_time = None

    def get_processed_total(self) -> int:
        """Get total number of documents that have been handled (processed, skipped, or errored).

        Returns:
            Total number of documents handled
        """
        with self._lock:
            return (
                self.documents_processed
                + self.documents_skipped
                + self.documents_errored
            )

    def increment_counter(self, counter_name: str, value: int = 1) -> None:
        """Thread-safe counter increment.

        Args:
            counter_name: Name of the counter to increment
            value: Value to increment by (default: 1)
        """
        with self._lock:
            current = getattr(self, counter_name)
            setattr(self, counter_name, current + value)

    def mark_complete(self):
        """Mark sync as complete and record end time."""
        with self._lock:
            if not self.end_time:
                self.end_time = time.time()

    def generate_report(self) -> str:
        """Generate a formatted report of sync statistics.

        Returns:
            Formatted statistics report
        """
        # Ensure end time is set
        if not self.end_time:
            self.mark_complete()

        with self._lock:
            duration = self.end_time - self.start_time
            minutes = int(duration // 60)
            seconds = int(duration % 60)

            report = [
                "\n===== Sync Statistics =====",
                f"Duration: {minutes} minutes {seconds} seconds",
                f"Started: {datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "Document Processing:",
                f"  - Total documents found: {self.total_documents}",
                f"  - Documents processed: {self.documents_processed}",
                f"  - Documents skipped: {self.documents_skipped}",
                f"  - Documents failed: {self.documents_errored}",
                "",
                "Database Operations:",
            ]

            # Add store stats if there were operations
            if any(
                [self.chroma_insertions, self.chroma_updates, self.chroma_deletions]
            ):
                report.extend(
                    [
                        "  Chroma:",
                        f"    - Insertions: {self.chroma_insertions}",
                        f"    - Updates: {self.chroma_updates}",
                        f"    - Deletions: {self.chroma_deletions}",
                    ]
                )

            if any(
                [
                    self.memgraph_nodes_created,
                    self.memgraph_relationships_created,
                    self.memgraph_deletions,
                ]
            ):
                report.extend(
                    [
                        "  Memgraph:",
                        f"    - Nodes Created: {self.memgraph_nodes_created}",
                        f"    - Relationships Created: {self.memgraph_relationships_created}",
                        f"    - Deletions: {self.memgraph_deletions}",
                    ]
                )

            report.extend(
                [
                    "",
                    "Chunking:",
                    f"  - Documents using LLM chunking: {self.llm_chunked_docs}",
                    f"  - Documents using token-based: {self.token_chunked_docs}",
                    f"  - Total LLM chunks created: {self.llm_chunks_created}",
                    f"  - Total token-based chunks created: {self.token_chunks_created}",
                    "",
                    "Rate Limiting:",
                    f"  - Number of rate limit hits: {self.rate_limit_hits}",
                    f"  - Total wait time: {self.rate_limit_wait_time:.1f} seconds",
                ]
            )

            return "\n".join(report)


# Create a module-level instance
_stats = SyncStats()


def get_stats() -> SyncStats:
    """Get the global stats instance.

    Returns:
        Global SyncStats instance
    """
    return _stats
