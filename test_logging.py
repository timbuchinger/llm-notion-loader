from src.utils.logging import get_logger, setup_logging

# Initialize logging with our config
setup_logging("logging.yaml")

# Get a logger
logger = get_logger("test")

# Test all log levels
logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("This is an error message")
logger.critical("This is a critical message")
