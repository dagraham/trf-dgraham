# trf/trf.py
import sys, os
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.layout import Layout
import logging

from . import init_db, close_db, setup_logging

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

    if len(sys.argv) < 2:
        print("Usage: track.py <db_file>")
        sys.exit(1)

    db_file = sys.argv[1]  # The first argument is the database file
    return trf_home, log_level, restore

def run_app(db_root):
    """
    Run the prompt_toolkit full-screen app.
    """
    textarea = TextArea(text="Welcome to the tracker app! Press Ctrl-C to exit.")

    # Wrap the TextArea in a Layout
    layout = Layout(container=textarea)

    # Create key bindings
    kb = KeyBindings()

    # Bind Ctrl-C to exit the application
    @kb.add('c-c')
    def _(event):
        event.app.exit()  # Exits the application

    # Create the Application with the correct layout and key bindings
    app = Application(layout=layout, full_screen=True, key_bindings=kb)

    # Access the database root and interact with it here...
    print(f"Database contains: {db_root.keys()}")  # Example of accessing the db root

    # Run the application
    app.run()


def main():
    # Get command-line arguments: Process the command-line arguments to get the database file location
    trf_home, log_level, restore = process_arguments()

    # Set up logging
    logger = setup_logging(trf_home=trf_home, log_level=log_level)

    # Initialize the ZODB database

    db_file = os.path.join(trf_home, "trf.fs")

    db, connection, db_root, transaction = init_db(db_file)

    try:
        # Step 3: Run the prompt_toolkit app
        run_app(db_root)
    finally:
        # Step 4: Close the database connection when the app exits
        close_db(db, connection)

if __name__ == "__main__":
    main()
