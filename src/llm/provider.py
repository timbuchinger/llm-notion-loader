import asyncio
import logging
import os
import time
from functools import wraps
from typing import Any, Callable, List, Type, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.llms import BaseLLM
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import OllamaLLM

from ..config import Config
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RateLimitedLLM:
    """Wrapper class that enforces rate limits on LLM invocations."""

    def __init__(
        self,
        llm: Union[OllamaLLM, ChatGoogleGenerativeAI, ChatGroq],
        provider: str,
        delay: float,
    ):
        self.llm = llm
        self.provider = provider
        self.delay = delay
        self.rate_limiter = RateLimiter()

    def invoke(self, prompt: Union[str, List[BaseMessage]], **kwargs) -> Any:
        """Invoke the LLM with rate limiting enforced."""
        if self.delay > 0:
            self.rate_limiter.wait_if_needed(self.provider, self.delay)
        return self.llm.invoke(prompt, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the wrapped LLM."""
        return getattr(self.llm, name)


class RateLimitCallback(BaseCallbackHandler):
    """Callback handler to track rate limit errors."""

    def __init__(self) -> None:
        from ..utils.stats import SyncStats

        self.stats = SyncStats()

    def on_llm_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> Any:
        """Called when LLM errors."""
        if "429" in str(error):  # Rate limit response
            self.stats.rate_limit_hits += 1
            if "in" in str(error) and "seconds" in str(error):
                try:
                    delay = float(str(error).split("in")[1].split("seconds")[0].strip())
                    self.stats.rate_limit_wait_time += delay
                except (IndexError, ValueError):
                    pass  # Failed to parse delay, skip tracking it


def get_llm() -> RateLimitedLLM:
    """Get the configured LLM provider instance.

    Returns:
        A language model instance based on the configured provider.

    Raises:
        ValueError: If the configured model provider is unknown.

    Note:
        Each provider handles retries differently, but we track rate limits
        through callbacks to gather statistics.
    """
    model_config = Config.get_model_config()
    model_provider = model_config["provider"]
    models = model_config.get("models", {})

    # Get rate limit configuration
    delay = model_config.get("rate_limits", {}).get(model_provider, 0)

    callbacks = [RateLimitCallback()]

    if model_provider == "ollama":
        llm = OllamaLLM(
            base_url=f"https://{os.environ.get('OLLAMA_HOST')}",
            model=models.get("ollama", "mistral:7b"),
            callbacks=callbacks,
        )

    elif model_provider == "gemini":
        llm = ChatGoogleGenerativeAI(
            model=models.get("gemini", "gemini-2.0-flash"),
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
            temperature=0,
            callbacks=callbacks,
        )

    elif model_provider == "groq":
        llm = ChatGroq(
            model_name=models.get("groq", "qwen-2.5-32b"),
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            temperature=0,
            callbacks=callbacks,
        )
    else:
        raise ValueError(f"Unknown model provider: {model_provider}")

    return RateLimitedLLM(llm, model_provider, delay)
