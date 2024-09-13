import ZODB, ZODB.FileStorage
import transaction
import logging
from logging.handlers import TimedRotatingFileHandler
import os, sys
# from try.try import TrackerManager

print(f"in __init__ with {sys.argv = }")

def process_arguments():
    """
    Process sys.argv to get the necessary parameters, like the database file location.
    """
    backup_count = 7

    if len(sys.argv) > 1:
        try:
            log_level = int(sys.argv[1])
            sys.argv.pop(1)
        except ValueError:
            print(f"Invalid log level: {sys.argv[1]}. Using default INFO level.")
            log_level = logging.INFO

    envhome = os.environ.get('TRFHOME')
    if len(sys.argv) > 1:
        trf_home = sys.argv[1]
    elif envhome:
        trf_home = envhome
    else:
        trf_home = os.getcwd()

    restore = len(sys.argv) > 2 and sys.argv[2] == 'restore'

    return trf_home, log_level, restore


def init_db(db_file):
    """
    Initialize the ZODB database using the specified file.
    """
    print("in init_db")
    storage = ZODB.FileStorage.FileStorage(db_file)
    db = ZODB.DB(storage)
    connection = db.open()
    root = connection.root()
    return storage, db, connection, root, transaction

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
    global db, connection, root, transaction
    print("in setup_logging")
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
        return filename.replace("trf.log.", "trf")

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

# Get command-line arguments: Process the command-line arguments to get the database file location
trf_home, log_level, restore = process_arguments()

# Set up logging
logger = setup_logging(trf_home=trf_home, log_level=log_level)

backup_dir = os.path.join(trf_home, "backup")

# Initialize the ZODB database

db_path = os.path.join(trf_home, "trf.fs")

storage, db, connection, root, transaction = init_db(db_path)

