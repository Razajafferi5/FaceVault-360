import logging
import sys

def setup_logging():
    """
    Setup structured logging for the application.
    """
    log_format = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Configure specific loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(logging.DEBUG)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully.")
