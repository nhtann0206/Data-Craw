import os
import logging
import sys
from src.utils.log_management import LogManager

# Create central log manager
log_manager = LogManager("log_management")

class Logger:
    def __init__(self, name: str, component: str = "system", level=logging.DEBUG):
        """Initialize logger with centralized logging system"""
        self.logger = log_manager.get_logger(name, component)
        self.logger.setLevel(level=level)
        self.logger.propagate = False  # Avoid duplicate logs
        
        # Ensure console output
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
        # Log the initialization
        self.logger.debug(f"Logger initialized for {name} in {component}")

    def get_logger(self):
        return self.logger

if __name__ == "__main__":
    # Test the logger
    logger = Logger(name="minio", component="storage").get_logger()
    logger.info("Ứng dụng bắt đầu")
    logger.debug("Testing log levels - DEBUG")
    logger.info("Testing log levels - INFO")
    logger.warning("Testing log levels - WARNING")
    logger.error("Testing log levels - ERROR")
