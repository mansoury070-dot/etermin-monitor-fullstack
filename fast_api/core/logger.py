import logging
import os
from logging.handlers import RotatingFileHandler

# Create a logs directory if it does not exist
if not os.path.exists("logs"):
    os.makedirs("logs")

# Define the log message format (time, logger name, level, and message)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Set up a handler to save logs to a file
# Max file size is 5MB, keeping up to 3 backup files to prevent disk space issues
file_handler = RotatingFileHandler(
    "logs/app.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(formatter)

# Set up a handler to output logs to the console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Create the main logger instance
logger = logging.getLogger("my_app_logger")
logger.setLevel(logging.INFO) # You can change this to logging.DEBUG for more details
logger.addHandler(file_handler)
logger.addHandler(console_handler)
