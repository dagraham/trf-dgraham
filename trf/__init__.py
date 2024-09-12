import ZODB, ZODB.FileStorage
import transaction
import logging
from logging.handlers import TimedRotatingFileHandler
import os


def init_db(db_file):
    """
    Initialize the ZODB database using the specified file.
    """
    storage = ZODB.FileStorage.FileStorage(db_file)
    db = ZODB.DB(storage)
    connection = db.open()
    root = connection.root()
    return db, connection, root, transaction

def close_db(db, connection):
    """
    Close the ZODB database and its connection.
    """
    connection.close()
    db.close()


def setup_logging(trf_home, log_level=logging.INFO, backup_count=7):
    """
    Set up logging with daily rotation and a specified log level.

    Args:
        trf_home (str): The home directory for storing log files.
        log_level (int): The log level (e.g., logging.DEBUG, logging.INFO).
        backup_count (int): Number of backup log files to keep.
    """
    log_dir = os.path.join(trf_home, "logs")

    # Ensure the logs directory exists
    os.makedirs(log_dir, exist_ok=True)

    logfile = os.path.join(log_dir, "trf.log")

    # Create a TimedRotatingFileHandler for daily log rotation
    handler = TimedRotatingFileHandler(
        logfile, when="midnight", interval=1, backupCount=backup_count
    )

    # Set the suffix to add the date and ".log" extension to the rotated files
    handler.suffix = "%y%m%d.log"

    # Create a formatter
    formatter = logging.Formatter(
        fmt='--- %(asctime)s - %(levelname)s - %(module)s.%(funcName)s\n    %(message)s',
        datefmt="%y-%m-%d %H:%M:%S"
    )

    # Set the formatter to the handler
    handler.setFormatter(formatter)

    # Define a custom namer function to change the log file naming format
    def custom_namer(filename):
        # Replace "tracker.log." with "tracker-" in the rotated log filename
        return filename.replace("trf.log.", "trf-")

    # Set the handler's namer function
    handler.namer = custom_namer

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear any existing handlers (if needed)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Add the TimedRotatingFileHandler to the logger
    logger.addHandler(handler)

    logger.info("Logging setup complete.")
    logging.info(f"\n### Logging initialized at level {log_level} ###")

    return logger
