import os
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Configuration paths
    LOG_CONFIG_PATH = "logging.yaml"
    CONFIG_PATH = str(Path(__file__).parent / "config" / "document_stores.yaml")

    # Default environment variables
    REQUIRED_ENV_VARS: Dict[str, str] = {
        "NOTION_API_TOKEN": os.environ.get("NOTION_API_TOKEN"),
        "CHROMA_AUTH_TOKEN": os.environ.get("CHROMA_AUTH_TOKEN"),
        "CHROMA_HOST": os.environ.get("CHROMA_HOST"),
        "CHROMA_COLLECTION": os.environ.get("CHROMA_COLLECTION", "notion"),
        "OLLAMA_HOST": os.environ.get("OLLAMA_HOST"),
        "AGE_HOST": os.environ.get("AGE_HOST", "localhost"),
        "AGE_PORT": os.environ.get("AGE_PORT", "5432"),
        "AGE_DATABASE": os.environ.get("AGE_DATABASE", "notion"),
        "AGE_USER": os.environ.get("AGE_USER", "postgres"),
        "AGE_PASSWORD": os.environ.get("AGE_PASSWORD"),
        # Neo4j environment variables (optional)
        "NEO4J_URI": os.environ.get("NEO4J_URI"),
        "NEO4J_USER": os.environ.get("NEO4J_USER"),
        "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD"),
        "NEO4J_DATABASE": os.environ.get("NEO4J_DATABASE", "notion"),
    }

    _config_cache: Optional[Dict[str, Any]] = None

    @classmethod
    def _load_config(cls, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file.

        Args:
            config_path: Optional path to config file. If None, uses default path.

        Returns:
            Loaded and processed configuration dictionary
        """
        if cls._config_cache is not None:
            return cls._config_cache

        try:
            config_path = config_path or cls.CONFIG_PATH
            with open(config_path) as f:
                # Load YAML content
                config_content = f.read()

                # Replace environment variables
                config_template = Template(config_content)
                config_with_env = config_template.safe_substitute(os.environ)

                # Parse YAML
                cls._config_cache = yaml.safe_load(config_with_env)
                return cls._config_cache
        except Exception as e:
            # Log error but don't fail - fall back to environment variables
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error loading config from {config_path}: {str(e)}")
            cls._config_cache = {
                "document_stores": {},
                "model": {
                    "provider": "ollama",
                    "models": {
                        "ollama": "mistral:7b",
                        "gemini": "gemini-2.0-flash",
                        "groq": "qwen-2.5-32b",
                    },
                },
            }
            return cls._config_cache

    @classmethod
    def get_model_config(cls) -> Dict[str, Any]:
        """Get model configuration.

        Returns:
            Model configuration dictionary containing provider and other settings
        """
        config = cls._load_config()
        return config.get(
            "model",
            {
                "provider": "ollama",
                "models": {
                    "ollama": "mistral:7b",
                    "gemini": "gemini-2.0-flash",
                    "groq": "qwen-2.5-32b",
                },
            },
        )

    @classmethod
    def get_store_config(cls, store_name: str) -> Dict[str, Any]:
        """Get configuration for a specific document store.

        Args:
            store_name: Name of the store (e.g., "chroma", "neo4j", "age")

        Returns:
            Store configuration dictionary
        """
        config = cls._load_config()
        return config.get("document_stores", {}).get(store_name, {})

    @classmethod
    def is_store_enabled(cls, store_name: str) -> bool:
        """Check if a document store is enabled.

        Args:
            store_name: Name of the store

        Returns:
            True if store is enabled, False otherwise
        """
        store_config = cls.get_store_config(store_name)
        return store_config.get("enabled", False)

    @classmethod
    def get_log_config_path(cls) -> str:
        """Get the logging configuration file path."""
        return os.environ.get("LOG_CONFIG_PATH", cls.LOG_CONFIG_PATH)

    @classmethod
    def validate_env(cls) -> None:
        """Validate that all required environment variables are set."""
        missing_vars = [
            var for var, value in cls.REQUIRED_ENV_VARS.items() if not value
        ]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

    @classmethod
    def get_env(cls, key: str) -> str:
        """Get environment variable value."""
        return cls.REQUIRED_ENV_VARS[key]

    # Convenience properties for commonly used values
    @property
    def notion_token(self) -> str:
        return self.get_env("NOTION_API_TOKEN")

    @property
    def chroma_collection(self) -> str:
        return self.get_env("CHROMA_COLLECTION")


def load_config() -> Dict[str, Any]:
    """Load and return the configuration.

    Returns:
        Configuration dictionary
    """
    return Config._load_config()
