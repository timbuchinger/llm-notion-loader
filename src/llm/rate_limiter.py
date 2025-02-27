import logging
import time
from typing import Dict

from ..utils.stats import SyncStats

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for LLM API calls."""

    _instance = None

    def __new__(cls):
        """Singleton pattern to ensure only one rate limiter exists."""
        if cls._instance is None:
            cls._instance = super(RateLimiter, cls).__new__(cls)
            cls._instance._last_call_times: Dict[str, float] = {}
        return cls._instance

    def wait_if_needed(self, provider: str, delay: float) -> None:
        """Wait for the remaining time if needed based on last call.

        Args:
            provider: The LLM provider name
            delay: The configured delay in seconds
        """
        current_time = time.time()
        last_call = self._last_call_times.get(provider, 0)

        # Calculate time since last call
        elapsed = current_time - last_call

        # Only sleep for remaining time if needed
        if elapsed < delay:
            remaining = delay - elapsed
            logger.info(f"Rate limiting: sleeping for {remaining:.1f}s before LLM call")

            # Update stats
            stats = SyncStats()
            stats.rate_limit_hits += 1
            stats.rate_limit_wait_time += remaining

            time.sleep(remaining)

        # Update last call time
        self._last_call_times[provider] = time.time()
