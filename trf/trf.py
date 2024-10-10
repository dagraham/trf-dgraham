# trf/trf.py
from typing import List, Dict, Any, Callable, Mapping
from collections import OrderedDict

import logging
from logging.handlers import TimedRotatingFileHandler
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    HSplit,
    VSplit,
    Window,
    DynamicContainer,
    WindowAlign,
    ConditionalContainer,
)
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
from prompt_toolkit.styles import Style
from prompt_toolkit.styles.named_colors import NAMED_COLORS
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.search import start_search, SearchDirection


from datetime import datetime, timedelta, date
import time
from prompt_toolkit.widgets import (
    TextArea,
    Frame,
    SearchToolbar,
    MenuContainer,
    MenuItem,
    HorizontalLine,
    Label
)

from prompt_toolkit.key_binding.bindings.focus import (
    focus_next,
    focus_previous,
)
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from io import StringIO
from dateutil.parser import parse, parserinfo
import string
import shutil
import threading
import traceback
    # initialize the tracker manager as a singleton instance
import textwrap
import sys
import os
import re
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.layout import Layout, Float, FloatContainer, Window
import logging
from persistent import Persistent
import pyperclip
import importlib.resources
import glob

import lorem
from lorem.text import TextLorem

from .__version__ import version

from . import trf_home, log_level, restore, backup_dir, db_path

# from . import storage, db, connection, root, transaction

from .backup import backup_to_zip, rotate_backups, restore_from_zip

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

import ZODB, ZODB.FileStorage
import transaction

freq = 12
mode = 'main'

def setup_logging(trf_home, log_level=logging.INFO, backup_count=7):
    """
    Set up logging with daily rotation and a specified log level.

    Args:
        trf_home (str): The home directory for storing log files.
        log_level (int): The log level (e.g., logging.DEBUG, logging.INFO).
        backup_count (int): Number of backup log files to keep.
    """
    global db, connection, root, transaction
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

# Set up logging
logger = setup_logging(trf_home=trf_home, log_level=log_level, backup_count=7)

def cleanup_old_logs():
    backup_count = 7
    log_dir = os.path.join(trf_home, "logs")
    log_files = sorted(glob.glob(os.path.join(log_dir, f"trf?*.log")))
    logger.debug(f"{log_files = }")
    if len(log_files) > backup_count:
        count = 0
        for log_file in log_files[:-backup_count]:
            count += 1
            os.remove(log_file)
            logger.debug(f"Removed old log file: {log_file}")
        logger.info(f"Cleaned up {count} old log files.")

def init_db(db_path):
    """
    Initialize the ZODB database using the specified file.
    """
    storage = ZODB.FileStorage.FileStorage(db_path)
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


def clear_screen():
    # For Windows
    if os.name == 'nt':
        os.system('cls')
    # For macOS and Linux (posix systems)
    else:
        os.system('clear')

# Initialize YAML object
yaml = YAML()

# Create a CommentedMap, which behaves like a Python dictionary but supports comments
settings_map = CommentedMap({
    'ampm': True,
    'yearfirst': True,
    'dayfirst': False,
    'η': 2,
})
# Add comments to the dictionary
settings_map.yaml_set_comment_before_after_key(
    'ampm',
    before='trf settings\n\n[ampm] Display 12-hour times with AM or PM if true, \notherwise display 24-hour times'
    )
settings_map.yaml_set_comment_before_after_key(
    'yearfirst',
    before='\n[yearfirst] When parsing ambiguous dates, assume the year is first \nif true, otherwise assume the month is first'
    )
settings_map.yaml_set_comment_before_after_key(
    'dayfirst',
    before='\n[dayfirst] When parsing ambiguous dates, assume the day is first \nif true, otherwise assume the month is first'
    )
settings_map.yaml_set_comment_before_after_key(
    'η',
    before='\n[η] Use this integer multiple of "spread" for setting the \ntimely-to-tardy next confidence interval'
    )


# this will be set in main() as a global variable
# logger = None

# Non-printing character
NON_PRINTING_CHAR = '\u200B'
# Placeholder for spaces within special tokens
PLACEHOLDER = '\u00A0'
# Placeholder for hyphens to prevent word breaks
NON_BREAKING_HYPHEN = '\u2011'
# Placeholder for zero-width non-joiner
ZWNJ = '\u200C'
PLUS_OR_MINUS = '±'

# For showing active page in pages, e.g.,  ○ ○ ⏺ ○ = page 3 of 4 pages
OPEN_CIRCLE = '○'
CLOSED_CIRCLE = '⏺'
ETA = 'η'
APPROX = '≈'

UP = '↑'
DOWN = '↓'
RIGHT = '→'


def wrap(text: str, indent: int = 3, width: int = shutil.get_terminal_size()[0] - 3):
    # Preprocess to replace spaces within specific "@\S" patterns with PLACEHOLDER
    text = preprocess_text(text)
    numbered_list = re.compile(r'^\d+\.\s.*')

    # Split text into paragraphs
    paragraphs = text.split('\n')

    # Wrap each paragraph
    wrapped_paragraphs = []
    for para in paragraphs:
        leading_whitespace = re.match(r'^\s*', para).group()
        initial_indent = leading_whitespace

        # Determine subsequent_indent based on the first non-whitespace character
        stripped_para = para.lstrip()
        if stripped_para.startswith(('+', '-', '*', '%', '!', '~')):
            subsequent_indent = initial_indent + ' ' * 2
        elif stripped_para.startswith(('@', '&')):
            subsequent_indent = initial_indent + ' ' * 3
        # elif stripped_para and stripped_para[0].isdigit():
        elif stripped_para and numbered_list.match(stripped_para):
            subsequent_indent = initial_indent + ' ' * 3
        else:
            subsequent_indent = initial_indent + ' ' * indent

        wrapped = textwrap.fill(
            para,
            initial_indent='',
            subsequent_indent=subsequent_indent,
            width=width)
        wrapped_paragraphs.append(wrapped)

    # Join paragraphs with newline followed by non-printing character
    wrapped_text = ('\n' + NON_PRINTING_CHAR).join(wrapped_paragraphs)

    # Postprocess to replace PLACEHOLDER and NON_BREAKING_HYPHEN back with spaces and hyphens
    wrapped_text = postprocess_text(wrapped_text)

    return wrapped_text

def preprocess_text(text):
    # Regex to find "@\S" patterns and replace spaces within the pattern with PLACEHOLDER
    text = re.sub(r'(@\S+\s\S+)', lambda m: m.group(0).replace(' ', PLACEHOLDER), text)
    # Replace hyphens within words with NON_BREAKING_HYPHEN
    text = re.sub(r'(\S)-(\S)', lambda m: m.group(1) + NON_BREAKING_HYPHEN + m.group(2), text)
        # logger.debug(f"listing {self.active_page = }, {start_index = }, {end_index = }")
    return text

def postprocess_text(text):
    text = text.replace(PLACEHOLDER, ' ')
    text = text.replace(NON_BREAKING_HYPHEN, '-')
    return text

def unwrap(wrapped_text):
    # Split wrapped text into paragraphs
    paragraphs = wrapped_text.split('\n' + NON_PRINTING_CHAR)

    # Replace newlines followed by spaces in each paragraph with a single space
    unwrapped_paragraphs = []
    for para in paragraphs:
        unwrapped = re.sub(r'\n\s*', ' ', para)
        unwrapped_paragraphs.append(unwrapped)

    # Join paragraphs with original newlines
    unwrapped_text = '\n'.join(unwrapped_paragraphs)

    return unwrapped_text

def sort_key(tracker):
    # Sorting by None first (using doc_id as secondary sorting)
    if tracker.next_expected_completion is None:
        return (0, tracker.doc_id)
    # Sorting by datetime for non-None values
    else:
        return (1, tracker.next_expected_completion)

# this is a singleton instance initialized in main()
class Tracker(Persistent):
    max_history = 12 # depending on width, 6 rows of 2, 4 rows of 3, 3 rows of 4, 2 rows of 6

    @classmethod
    def format_dt(cls, dt: Any, long=False) -> str:
        if not isinstance(dt, datetime):
            return ""
        if long:
            return dt.strftime("%Y-%m-%d %H:%M")
        return dt.strftime("%y%m%dT%H%M")

    @classmethod
    def td2seconds(cls, td: timedelta) -> str:
        if not isinstance(td, timedelta):
            return ""
        return f"{round(td.total_seconds())}"

    @classmethod
    def format_td(cls, td: timedelta, short=0):
        if not isinstance(td, timedelta):
            return None
        sign = '+' if td.total_seconds() >= 0 else '-'
        total_seconds = abs(int(td.total_seconds()))
        if total_seconds == 0:
            # return '0 minutes '
            return '0m' if short else '+0m'
        total_seconds = abs(total_seconds)
        try:
            until = []
            days = hours = minutes = 0
            if total_seconds:
                minutes = total_seconds // 60
                if minutes >= 60:
                    hours = minutes // 60
                    minutes = minutes % 60
                if hours >= 24:
                    days = hours // 24
                    hours = hours % 24
            if days:
                until.append(f'{days}d')
            if hours:
                until.append(f'{hours}h')
            if minutes:
                until.append(f'{minutes}m')
            if not until:
                until.append('0m')
            if short == 1:
                ret = ''.join(until[:2]) if short else sign + ''.join(until)
            elif short == 2:
                ret = f"{round(days + hours/24 + minutes/(60*24), 1)}"
            elif short == 3:
                ret = f"{round(days + hours/24 + minutes/(60*24), 1)}d"
            logger.debug(f'{td = }, {short = }: {ret = }')
            return ret
        except Exception as e:
            logger.error(f'{td}: {e}')
            return ''

    @classmethod
    def format_completion(cls, completion: tuple[datetime, timedelta], long=False)->str:
        dt, td = completion
        return f"{cls.format_dt(dt, long=True)}, {cls.format_td(td)}"

    @classmethod
    def parse_td(cls, td:str)->tuple[bool, timedelta]:
        """\
        Take a period string and return a corresponding timedelta.
        Examples:
            parse_duration('-2w3d4h5m')= Duration(weeks=-2,days=3,hours=4,minutes=5)
            parse_duration('1h30m') = Duration(hours=1, minutes=30)
            parse_duration('-10m') = Duration(minutes=10)
        where:
            d: days
            h: hours
            m: minutes
            s: seconds

        >>> 3*60*60+5*60
        11100
        >>> parse_duration("2d-3h5m")[1]
        Duration(days=1, hours=21, minutes=5)
        >>> datetime(2015, 10, 15, 9, 0, tz='local') + parse_duration("-25m")[1]
        DateTime(2015, 10, 15, 8, 35, 0, tzinfo=ZoneInfo('America/New_York'))
        >>> datetime(2015, 10, 15, 9, 0) + parse_duration("1d")[1]
        DateTime(2015, 10, 16, 9, 0, 0, tzinfo=ZoneInfo('UTC'))
        >>> datetime(2015, 10, 15, 9, 0) + parse_duration("1w-2d+3h")[1]
        DateTime(2015, 10, 20, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
        """

        knms = {
            'd': 'days',
            'day': 'days',
            'days': 'days',
            'h': 'hours',
            'hour': 'hours',
            'hours': 'hours',
            'm': 'minutes',
            'minute': 'minutes',
            'minutes': 'minutes',
            's': 'seconds',
            'second': 'second',
            'seconds': 'seconds',
        }

        kwds = {
            'days': 0,
            'hours': 0,
            'minutes': 0,
            'seconds': 0,
        }

        period_regex = re.compile(r'(([+-]?)(\d+)([dhms]))+?')
        expanded_period_regex = re.compile(r'(([+-]?)(\d+)\s(day|hour|minute|second)s?)+?')
        # logger.debug(f"parse_td: {td}")
        m = period_regex.findall(td)
        if not m:
            m = expanded_period_regex.findall(str(td))
            if not m:
                return False, f"Invalid period string '{td}'"
        for g in m:
            if g[3] not in knms:
                return False, f'Invalid period argument: {g[3]}'

            num = -int(g[2]) if g[1] == '-' else int(g[2])
            if num:
                kwds[knms[g[3]]] = num
        td = timedelta(**kwds)
        return True, td


    @classmethod
    def parse_dt(cls, dt: str = "") -> tuple[bool, datetime]:
        # if isinstance(dt, datetime):
        #     return True, dt
        if dt.strip() == "now":
            dt = datetime.now()
            return True, dt
        elif isinstance(dt, str) and dt:
            pi = parserinfo(
                dayfirst=False,
                yearfirst=True)
            try:
                dt = parse(dt, parserinfo=pi)
                return True, dt
            except Exception as e:
                msg = f"Error parsing datetime: {dt}\ne {repr(e)}"
                return False, msg
        else:
            return False, "Invalid datetime"

    @classmethod
    def parse_completion(cls, completion: str) -> tuple[datetime, timedelta]:
        parts = [x.strip() for x in re.split(r',\s+', completion)]
        dt = parts.pop(0)
        if parts:
            td = parts.pop(0)
        else:
            td = timedelta(0)

        # logger.debug(f"parts: {dt}, {td}")
        msg = []
        if not dt:
            return False, ""
        dtok, dt = cls.parse_dt(dt)
        if not dtok:
            msg.append(dt)
        if td:
            # logger.debug(f"{td = }")
            tdok, td = cls.parse_td(td)
            if not tdok:
                msg.append(td)
        else:
            # no td specified
            td = timedelta(0)
            tdok = True
        if dtok and tdok:
            return True, (dt, td)
        return False, "; ".join(msg)

    @classmethod
    def parse_completions(cls, completions: List[str]) -> List[tuple[datetime, timedelta]]:
        completions = [x.strip() for x in completions.split('\n') if x.strip()]
        output = []
        msg = []
        for completion in completions:
            ok, x = cls.parse_completion(completion)
            if ok:
                output.append(x)
            else:
                msg.append(x)
        if msg:
            return False, "; ".join(msg)
        return True, output


    def __init__(self, name: str, doc_id: int) -> None:
        self.doc_id = int(doc_id)
        self.name = name
        self.history = []
        self.created = datetime.now()
        self.modified = self.created
        logger.info(f"Created tracker {self.name} ({self.doc_id})")


    @property
    def info(self):
        # Lazy initialization with re-computation logic
        if not hasattr(self, '_info') or self._info is None:
            # logger.debug(f"Computing info for {self.name} ({self.doc_id})")
            self._info = self.compute_info()
        return self._info

    def compute_info(self):
        # Example computation based on history, returning a dict
        result = {}
        logger.debug(f"Computing info for {self.name} ({self.doc_id})")
        if not self.history:
            result = dict(
                last_completion=None, num_completions=0, num_intervals=0, average_interval=timedelta(minutes=0), last_interval=timedelta(minutes=0), spread=timedelta(minutes=0), next_expected_completion=None,
                early=None, timely=None, tardy=None, avg=None, plus_or_minus=f"{5*' '}~{5*' '}"
                )
        else:
            result['last_completion'] = self.history[-1] if len(self.history) > 0 else None
            result['num_completions'] = len(self.history)
            result['intervals'] = []
            result['num_intervals'] = 0
            result['spread'] = timedelta(minutes=0)
            result['last_interval'] = None
            result['average_interval'] = None
            result['next_expected_completion'] = None
            result['early'] = None
            result['timely'] = None
            result['tardy'] = None
            result['avg'] = None
            result['plus_or_minus'] = f"{5*' '}~{5*' '}"
            if result['num_completions'] > 0:
                for i in range(len(self.history)-1):
                    #                      x[i+1]                  y[i+1]               x[i]
                    # logger.debug(f"{self.history[i+1]}")
                    result['intervals'].append(self.history[i+1][0] + self.history[i+1][1] - self.history[i][0])
                result['num_intervals'] = len(result['intervals'])
            if result['num_intervals'] > 0:
                # result['last_interval'] = intervals[-1]
                if result['num_intervals'] == 1:
                    result['average_interval'] = result['intervals'][-1]
                else:
                    result['average_interval'] = sum(result['intervals'], timedelta()) / result['num_intervals']
                result['next_expected_completion'] = result['last_completion'][0] + result['average_interval']
                result['timely'] = result['next_expected_completion'] - timedelta(days=1)
                result['tardy'] = result['next_expected_completion'] + timedelta(days=1)
                change = result['intervals'][-1] - result['average_interval']
                direction = UP if change > timedelta(0) else DOWN if change < timedelta(0) else RIGHT
                result['avg'] = f"{Tracker.format_td(result['average_interval'], 2)}{direction}"
                # logger.debug(f"{result['avg'] = }")
                result['plus_or_minus'] = f"{Tracker.format_td(result['average_interval'], 3): ^11}"
            if result['num_intervals'] >= 2:
                total = timedelta(minutes=0)
                for interval in result['intervals']:
                    if interval < result['average_interval']:
                        total += result['average_interval'] - interval
                    else:
                        total += interval - result['average_interval']
                result['spread'] = total / result['num_intervals']
                result['n_x_spread'] = tracker_manager.settings['η'] * result['spread']
                result['n_spread'] = f"{tracker_manager.settings['η']} × {Tracker.format_td(result['spread'], 3)} = {Tracker.format_td(result['n_x_spread'], 3)}"

                result['plus_or_minus'] = f"{Tracker.format_td(result['average_interval'], 2): >5}{PLUS_OR_MINUS}{Tracker.format_td(result['n_x_spread'], 3): <5}"

            if result['num_intervals'] >= 1:
                result['early']  = result['next_expected_completion'] - (tracker_manager.settings['η']*2) * result['spread']
                result['timely'] = result['next_expected_completion'] - tracker_manager.settings['η'] * result['spread']
                result['tardy'] = result['next_expected_completion'] + tracker_manager.settings['η'] * result['spread']
        logger.debug(f"returning {result['plus_or_minus'] = }")

        self._info = result
        self._p_changed = True
        logger.debug(f"returning {result = }")

        return result

    # XXX: Just for reference
    def add_to_history(self, new_event):
        self.history.append(new_event)
        self.modified = datetime.now()
        self.invalidate_info()
        self._p_changed = True  # Mark object as changed in ZODB

    def format_history(self)->str:
        output = []
        for completion in self.history:
            output.append(Tracker.format_completion(completion, long=True))
        return '\n  '.join(output)

    def invalidate_info(self):
        # Invalidate the cached dict so it will be recomputed on next access
        if hasattr(self, '_info'):
            delattr(self, '_info')
        self.compute_info()


    def record_completion(self, completion: tuple[datetime, timedelta]):
        ok, msg = True, ""
        if not isinstance(completion, tuple) or len(completion) < 2:
            completion = (completion, timedelta(0))
        self.history.append(completion)
        self.history.sort(key=lambda x: x[0])
        if len(self.history) > Tracker.max_history:
            self.history = self.history[-Tracker.max_history:]

        # Notify ZODB that this object has changed
        self.invalidate_info()
        self.modified = datetime.now()
        self._p_changed = True
        return True, f"recorded completion for ..."

    def rename(self, name: str):
        original_name = self.name
        self.name = name
        self.invalidate_info()
        self.modified = datetime.now()
        self._p_changed = True
        return True, f"renamed {self.doc_id} from {original_name} to {self.name}"

    def record_completions(self, completions: list[tuple[datetime, timedelta]]):
        logger.debug(f"starting {self.history = }")
        self.history = []
        for completion in completions:
            if not isinstance(completion, tuple) or len(completion) < 2:
                completion = (completion, timedelta(0))
            self.history.append(completion)
        self.history.sort(key=lambda x: x[0])
        if len(self.history) > Tracker.max_history:
            self.history = self.history[-Tracker.max_history:]
        logger.debug(f"ending {self.history = }")
        self.invalidate_info()
        self.modified = datetime.now()
        self._p_changed = True
        return True, f"recorded completions for ..."

    def remove_completions(self):
        self.history = []
        self.invalidate_info()
        self.modified = datetime.now()
        self._p_changed = True
        return True, f"removed all completions for ..."


    def edit_history(self):
        if not self.history:
            # logger.debug("No history to edit.")
            return

        # Display current history
        for i, completion in enumerate(self.history):
            logger.debug(f"{i + 1}. {self.format_completion(completion)}")

        # Choose an entry to edit
        try:
            choice = int(input("Enter the number of the history entry to edit (or 0 to cancel): ").strip())
            if choice == 0:
                return
            if choice < 1 or choice > len(self.history):
                return
            selected_comp = self.history[choice - 1]

            # Choose what to do with the selected entry
            action = input("Do you want to (d)elete or (r)eplace this entry? ").strip().lower()

            if action == 'd':
                self.history.pop(choice - 1)
            elif action == 'r':
                new_comp_str = input("Enter the replacement completion: ").strip()
                ok, new_comp = self.parse_completion(new_comp_str)
                if ok:
                    self.history[choice - 1] = new_comp
                    return True, f"Entry replaced with {self.format_completion(new_comp)}"
                else:
                    return False, f"{new_comp}"
            else:
                return False, "Invalid action."

            # Sort and truncate history if necessary
            self.history.sort()
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

            # Notify ZODB that this object has changed
            self.modified = datetime.now()
            self.update_tracker_info()
            self.invalidate_info()
            self._p_changed = True

        except ValueError:
            logger.error("Invalid input. Please enter a number.")

    def get_tracker_info(self):

        if not hasattr(self, '_info') or self._info is None:
            self._info = self.compute_info()
        logger.debug(f"{self._info = }")
        logger.debug(f"{self._info['avg'] = }")
        # insert a placeholder to prevent date and time from being split across multiple lines when wrapping
        # format_str = f"%y-%m-%d{PLACEHOLDER}%H:%M"
        # logger.debug(f"{self.history = }")
        history = [f"{Tracker.format_dt(x[0])} {Tracker.format_td(x[1])}" for x in self.history] if self.history else []
        history = ', '.join(history)
        intervals = [f"{Tracker.format_td(x, 3)}" for x in self._info['intervals']] if self._info.get('intervals') else []
        intervals = ', '.join(intervals) if intervals else ""
        return wrap(f"""\
 name:        {self.name}
 doc_id:      {self.doc_id}
 created:     {Tracker.format_dt(self.created)}
 modified:    {Tracker.format_dt(self.modified)}
 completions: ({self._info['num_completions']})
    {history}
 intervals:   ({self._info['num_intervals']})
    {intervals}
    average:  {self._info['avg']}
    spread:   {Tracker.format_td(self._info['spread'], 3)}
    η spread: {self._info.get('n_spread', '?')}
 next:    {Tracker.format_dt(self._info['next_expected_completion'])}
    early:    next - 2 × η spread = {Tracker.format_dt(self._info.get('early', '?'))}
    timely:   next - η spread     = {Tracker.format_dt(self._info.get('timely', '?'))}
    tardy:    next + η spread     = {Tracker.format_dt(self._info.get('tardy', '?'))}
""", 0)

def page_banner(active_page_num: int, number_of_pages: int, sort_by: str):
    return f"{active_page_num}/{number_of_pages}: {sort_by}"

class TrackerManager:

    def __init__(self, storage, db, connection, root, transaction) -> None:
        # Ensure that all required arguments are provided during the first initialization
        if db is None or connection is None or root is None or transaction is None:
            raise ValueError("db, connection, root, and transaction must be provided on the first initialization.")

        # Initialize instance attributes
        self.storage = storage
        self.db = db
        self.connection = connection
        self.root = root
        self.transaction = transaction
        self.trackers = {}
        self.tag_to_id = {}
        self.row_to_id = {}
        self.id_to_row = {}
        self.tag_to_row = {}
        self.id_to_times = {}
        self.active_page = 0
        self.num_pages = 0
        self.selected_id = None
        self.selected_tracker = None
        self.selected_row = (None, None)
        self.sort_by = "next"
        logger.info(f"using data from\n  {self.db}")
        self.load_data()

    def load_data(self):
        try:
            if 'settings' not in self.root:
                self.root['settings'] = settings_map
                self.transaction.commit()
            self.settings = self.root['settings']
            if 'trackers' not in self.root:
                self.root['trackers'] = {}
                self.root['next_id'] = 1  # Initialize the ID counter
                self.transaction.commit()
            self.trackers = self.root['trackers']
        except Exception as e:
            logger.error(f"Warning: could not load data from '{db_path}': {str(e)}")
            self.trackers = {}

    def restore_defaults(self):
        self.root['settings'] = settings_map
        self.settings = self.root['settings']
        self.transaction.commit()
        logger.info(f"Restored default settings:\n{self.settings}")
        self.refresh_info()

    def refresh_info(self):
        for k, v in self.trackers.items():
            v.compute_info()
        logger.info("Refreshed tracker info.")

    def set_setting(self, key, value):

        if key in self.settings:
            self.settings[key] = value
            self.zodb_root[0] = self.settings  # Update the ZODB storage
            self.transaction.commit()
        else:
            logger.error(f"Setting '{key}' not found.")

    def get_setting(self, key):
        return self.settings.get(key, None)

    def add_tracker(self, name: str) -> None:
        doc_id = self.root['next_id']
        # Create a new tracker with the current doc_id
        tracker = Tracker(name, doc_id)
        # Add the tracker to the trackers dictionary
        self.trackers[doc_id] = tracker
        # Increment the next_id for the next tracker
        self.root['next_id'] += 1
        # Save the updated data
        self.save_data()

        logger.info(f"Tracker '{name}' added with ID {doc_id}")
        return doc_id

    def rename_tracker(self, doc_id: int, new_name: str):
        ok, msg = self.trackers[doc_id].rename(new_name)
        if not ok:
            display_message(msg, 'error')
            return
        display_message(f"{self.trackers[doc_id].get_tracker_info()}", 'info')


    def record_completion(self, doc_id: int, comp: tuple[datetime, timedelta]):
        # dt will be a datetime
        ok, msg = self.trackers[doc_id].record_completion(comp)
        if not ok:
            display_message(msg)
            return
        # self.trackers[doc_id].compute_info()
        display_message(f"{self.trackers[doc_id].get_tracker_info()}", 'info')

    def record_completions(self, doc_id: int, completions: list[tuple[datetime, timedelta]]):
        ok, msg = self.trackers[doc_id].record_completions(completions)
        if not ok:
            display_message(msg, 'error')
            return
        display_message(f"{self.trackers[doc_id].get_tracker_info()}", 'info')

    def remove_completions(self, doc_id: int):
        ok, msg = self.trackers[doc_id].remove_completions()
        if not ok:
            display_message(msg, 'error')
            return
        display_message(f"{self.trackers[doc_id].get_tracker_info()}", 'info')


    def get_tracker_data(self, doc_id: int = None):
        if doc_id is None:
            # logger.debug("data for all trackers:")
            for k, v in self.trackers.items():
                logger.debug(f"   {k:2> }. {v.get_tracker_data()}")
        elif doc_id in self.trackers:
            logger.debug(f"data for tracker {doc_id}:")
            logger.debug(f"   {doc_id:2> }. {self.trackers[doc_id].get_tracker_data()}")

    def sort_key(self, tracker):
        forecast_dt = tracker._info.get('next_expected_completion', None) if hasattr(tracker, '_info') else None
        last_dt = tracker._info.get('last_completion', None) if hasattr(tracker, '_info') else None
        early_dt = tracker._info.get('timely', None) if hasattr(tracker, '_info') else None
        if self.sort_by == "next":
            if forecast_dt:
                return (0, forecast_dt)
            if last_dt:
                return (1, last_dt)
            return (2, tracker.doc_id)
        if self.sort_by == "last":
            if last_dt:
                return (0, last_dt)
            if forecast_dt:
                return (1, forecast_dt)
            return (2, tracker.doc_id)
        if self.sort_by == "subject":
            return (0, tracker.name)
        if self.sort_by == "id":
            return (1, tracker.doc_id)
        if self.sort_by == "modified":
            return (1, tracker.modified)
        else: # next
            if forecast_dt:
                return (0, forecast_dt)
            if last_dt:
                return (1, last_dt)
            return (2, tracker.doc_id)

    def get_sorted_trackers(self):
        # Extract the list of trackers
        trackers = [v for k, v in self.trackers.items()]
        # Sort the trackers
        reverse = True if self.sort_by == "modified" else False
        return sorted(trackers, key=self.sort_key, reverse=reverse)

    def list_trackers(self):
        name_width = shutil.get_terminal_size()[0] - 45
        self.num_pages = (len(self.trackers) + 25) // 26

        sort = self.sort_by + UP if self.sort_by == 'modified' else self.sort_by + DOWN
        n = self.settings.get('η', None)
        if n:
            interval = f" η={n} {int(round(100*(1 - 1/(n*n)), 0))}%"
            # interval = f"{int(round(100*(1 - 1/(n*n)), 0))}% span"
        else: #        " n=3 89%"
            interval = "interval"

        set_pages(page_banner(self.active_page + 1, self.num_pages, sort))
        banner = f"{ZWNJ} tag     next      {interval}     last        subject\n"
        rows = []

        count = 0

        start_index = self.active_page * 26
        end_index = start_index + 26
        sorted_trackers = self.get_sorted_trackers()
        sigma = self.settings.get('η', 1)
        logger.debug(f"listing {self.active_page = }, {start_index = }, {end_index = }")
        for tracker in sorted_trackers[start_index:end_index]:
            parts = [x.strip() for x in tracker.name.split('@')]
            tracker_name = parts[0]
            if len(tracker_name) > name_width:
                tracker_name = tracker_name[:name_width - 1] + "…"
            forecast_dt = tracker._info.get('next_expected_completion', None) if hasattr(tracker, '_info') else None
            early = tracker._info.get('early', '') if hasattr(tracker, '_info') else ''
            timely = tracker._info.get('timely', '') if hasattr(tracker, '_info') else ''
            tardy = tracker._info.get('tardy', '') if hasattr(tracker, '_info') else ''
            plus_or_minus = tracker._info.get('plus_or_minus', '') if hasattr(tracker, '_info') else f"{5*' '}~{5*' '}"
            average = tracker._info.get('average_interval', '') if hasattr(tracker, '_info') else ''
            if tracker.history:
                last = tracker.history[-1][0].strftime("%y-%m-%d")
            else:
                last = "~"
            next = forecast_dt.strftime("%y-%m-%d") if forecast_dt else center_text("~", 8)
            avg = tracker._info.get('avg', None) if hasattr(tracker, '_info') else None
            interval = f"{avg: <8}" if avg else f"{'~': ^8}"
            tag = tag_keys[count]
            self.id_to_times[tracker.doc_id] = (
                early.strftime("%y-%m-%d") if early else '',
                timely.strftime("%y-%m-%d") if timely else '',
                tardy.strftime("%y-%m-%d") if tardy else '')
            self.tag_to_id[(self.active_page, tag)] = tracker.doc_id
            self.row_to_id[(self.active_page, count+1)] = tracker.doc_id
            self.id_to_row[tracker.doc_id] =  (self.active_page, count+1)
            self.tag_to_row[(self.active_page, tag)] = (self.active_page, count+1) # count+1
            count += 1
            # rows.append(f" {tag}{" "*4}{next}{" "*2}{last}{" "*2}{interval}{" " * 3}{tracker_name}")
            #             1  1    4         13      2       8       2      8       3
            this_row = f" {tag}{' '*4}{next}{' '*2}{plus_or_minus}{' '*2}{last}{' ' * 3}{tracker_name}"
            rows.append(this_row)
            logger.debug(f"{len(next) = }; {len(plus_or_minus) = }; {len(last) = }; {len(rows[-1]) = }")
        if self.selected_id:
            self.selected_row = self.id_to_row[self.selected_id]
        return banner +"\n".join(rows)

    def set_active_page(self, page_num):
        logger.debug(f"set_active_page {page_num = }")
        if 0 <= page_num < (len(self.trackers) + 25) // 26:
            self.active_page = page_num
            logger.debug(f"setting active page to {page_num = }, {self.active_page = }")
            display_area.buffer.cursor_position = (
                display_area.buffer.document.translate_row_col_to_index(0, 0)
            )

    def get_active_page(self):
        return self.active_page

    def next_page(self):
        # new_page = min(self.get_active_page() + 1, self.num_pages - 1)
        self.set_active_page(self.get_active_page() + 1)
        self.selected_id = None
        self.selected_row = (self.active_page, 0)
        logger.debug(f"next page: {self.active_page = }")

    def previous_page(self):
        self.set_active_page(self.get_active_page() - 1)
        self.selected_row = (self.active_page, 0)
        self.selected_id = None

        logger.debug(f"previous page: {self.active_page = }")

    def set_page(self, page_num):
        self.set_active_page(page_num)
        self.selected_id = None
        self.selected_row = (self.active_page, 0)
        logger.debug(f"set page: {self.active_page = }")

    def first_page(self):
        self.set_active_page(0)
        self.selected_id = None
        self.selected_row = (self.active_page, 0)
        logger.debug(f"first page: {self.selected_row = }")


    def get_tracker_from_tag(self, tag: str):
        pagetag = (self.active_page, tag)
        if pagetag not in self.tag_to_id:
            return None
        self.selected_id = self.tag_to_id[pagetag]
        self.selected_tracker = self.trackers[self.tag_to_id[pagetag]]
        self.selected_row = pagetag
        return self.trackers[self.tag_to_id[pagetag]]

    def get_tracker_from_row(self):
        row = display_area.document.cursor_position_row
        pagerow = (self.active_page, row)
        if pagerow not in self.row_to_id:
            return None
        # logger.debug(f"{self.row_to_id = }; {pagerow = }")
        self.selected_row = pagerow
        self.selected_id = self.row_to_id[pagerow]
        self.selected_tracker = self.trackers[self.row_to_id[pagerow]]
        logger.debug(f"returning {self.selected_tracker.doc_id = }; {self.selected_tracker.name = }")
        return self.trackers[self.row_to_id[pagerow]]

    def save_data(self):
        logger.info(f"Saving data: {self.trackers = }")
        self.root['trackers'] = self.trackers
        self.transaction.commit()

    def update_tracker(self, doc_id, tracker):
        self.trackers[doc_id] = tracker
        self.save_data()

    def delete_tracker(self, doc_id):
        if doc_id in self.trackers:
            del self.trackers[doc_id]
            self.save_data()

    def edit_tracker_history(self, label: str):
        tracker = self.get_tracker_from_tag(label)
        if tracker:
            tracker.edit_history()
            self.save_data()
        else:
            logger.error(f"No tracker found corresponding to label {label}.")

    def get_tracker_from_id(self, doc_id):
        # logger.debug(f"get_tracker_from_id: {doc_id = }; {self.trackers = }")
        self.selected_id = doc_id
        tracker = self.trackers.get(doc_id, None)
        logger.debug(f"get_tracker_from_id: {doc_id = }; {tracker = }")
        return tracker

    def get_row_from_id(self, doc_id):
        page, row = self.id_to_row.get(doc_id, (None, None))

    def close(self):
        # Make sure to commit or abort any ongoing transaction
        try:
            if self.connection.transaction_manager.isDoomed():
                logger.error("Transaction aborted.")
                self.transaction.abort()
            else:
                logger.info("Transaction committed.")
                self.transaction.commit()
        except Exception as e:
            logger.error(f"Error during transaction handling: {e}")
            self.transaction.abort()
        else:
            logger.info("Transaction handled successfully.")
        finally:
            self.connection.close()
            self.db.close()

# Initialize the ZODB database
storage, db, connection, root, transaction = init_db(db_path)

tracker_manager = TrackerManager(storage, db, connection, root, transaction)

tag_keys = list(string.ascii_lowercase)

# Application Setup
tracker_style = {
    'next-hot': 'fg:darkorange',
    'next-warm': 'fg:gold',
    'next-cool': 'fg:lightskyblue',
    'next-cold': 'fg:lightcyan',
    'last-less': '',
    'last-more': '',
    'no-dates': '',
    'default': '',
    'banner': 'fg:limegreen',
    'tag': 'fg:gray',
}

highlight_style = {}
for k, v in tracker_style.items():
    # highlight_style[k] = tracker_style[k] + ' bg:#ffffcc' # Almost white
    # highlight_style[k] = tracker_style[k] + ' bg:#545655' # Shades of gray
    # highlight_style[k] = tracker_style[k] + ' bg:#606361'
    # highlight_style[k] = tracker_style[k] + ' bg:#959896'
    highlight_style[k] = tracker_style[k] + ' bg:gray'

def is_current_row(line_number: int):
    cursor_row = display_area.document.cursor_position_row
    # logger.debug(f"{line_number = }, {cursor_row = }")
    return int(line_number) == int(cursor_row)

banner_regex = re.compile(r'^\u200C')

class DefaultLexer(Lexer):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DefaultLexer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            now = datetime.now()
        now = datetime.now()

    def lex_document(self, document):
        # Implement the logic for tokenizing the document here.
        # You should yield tuples of (start_pos, Token) pairs for each token in the document.

        # Example: Basic tokenization that highlights keywords in a simple way.
        text = document.text
        for i, line in enumerate(text.splitlines()):
            if "keyword" in line:
                yield i, ('class:keyword', line)
            else:
                yield i, ('', line)


class InfoLexer(Lexer):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(InfoLexer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            now = datetime.now()
        now = datetime.now()

    def lex_document(self, document):
        # Implement the logic for tokenizing the document here.
        # You should yield tuples of (start_pos, Token) pairs for each token in the document.

        # Example: Basic tokenization that highlights keywords in a simple way.
        # logger.debug("lex_document called")
        active_page = tracker_manager.active_page
        lines = document.lines
        now = datetime.now().strftime("%y-%m-%d")
        def get_line_tokens(line_number):
            line = lines[line_number]
            tokens = []
            if line:
                tokens.append((tracker_style.get('default', ''), line))
            return tokens
        return get_line_tokens


class HelpLexer(Lexer):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(HelpLexer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            now = datetime.now()
        now = datetime.now()

    def lex_document(self, document):
        # Implement the logic for tokenizing the document here.
        # You should yield tuples of (start_pos, Token) pairs for each token in the document.

        # Example: Basic tokenization that highlights keywords in a simple way.
        # logger.debug("lex_document called")
        active_page = tracker_manager.active_page
        lines = document.lines
        now = datetime.now().strftime("%y-%m-%d")
        def get_line_tokens(line_number):
            line = lines[line_number]
            tokens = []
            if line:
                tokens.append((tracker_style.get('default', ''), line))
            return tokens
        return get_line_tokens



def get_lexer(document_type):
    # logger.debug(f"get_lexer: {document_type}")
    if document_type == 'list':
        return TrackerLexer()
    elif document_type == 'info':
        return InfoLexer()
    else:
        return DefaultLexer()

class TrackerLexer(Lexer):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TrackerLexer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            now = datetime.now()

    def lex_document(self, document):
        # logger.debug("lex_document called")
        active_page = tracker_manager.active_page
        lines = document.lines
        now = datetime.now().strftime("%y-%m-%d")
        width = shutil.get_terminal_size()[0] - 1
        def get_line_tokens(line_number):
            line = lines[line_number]
            tokens = []
            if is_current_row(line_number):
                # Apply style to the whole line with a background for the current line
                list_style = highlight_style
                line = f"{line:<{width}}"
            else:
                list_style = tracker_style
                # Apply no special style for other lines
                # return [('class:default', line)]

            if line and line[0] == ' ':  # does line start with a space
                parts = line.split()
                if len(parts) < 5:
                    return [(list_style.get('default', ''), line)]

                # Extract the parts of the line
                tag, next_date, interval, last_date, tracker_name = parts[0], parts[1], parts[2], parts[3], " ".join(parts[4:])
                tracker_name = f"   {tracker_name:<{width-44}}"
                id = tracker_manager.tag_to_id.get((active_page, tag), None)
                early, timely, tardy = tracker_manager.id_to_times.get(id, (None,None, None))
                # logger.debug(f"{width = }, {tracker_name = },  ")

                # Determine styles based on dates
                if early and timely and tardy:
                    if now < early:
                        this_style = list_style.get('next-cold', '')
                    if early <= now and now < timely:
                        this_style = list_style.get('next-cool', '')
                    elif timely <= now and now < tardy:
                        this_style = list_style.get('next-warm', '')
                    elif tardy <= now:
                        this_style = list_style.get('next-hot', '')
                elif next_date != "~" and next_date > now:
                    this_style = list_style.get('next-cool', '')
                else:
                    this_style = list_style.get('default', '')
                next_style = this_style
                last_style = this_style
                spread_style = this_style
                name_style = this_style
                # logger.debug(f"{early = }, {timely = }, {tardy = }: {this_style = }")

                # Format each part with fixed width
                tag_formatted = f"  {tag}  "          # 7 spaces for tag
                next_formatted = f"  {next_date: ^8}"  # 10 spaces for next date
                if "±" in interval:
                    iparts = interval.split("±")
                    spread_formatted = f"  {iparts[0]: >5}±{iparts[1]: <5}"
                else:
                    spread_formatted = f"  {interval: ^11}"
                last_formatted = f"  {last_date: ^8}"
                # Add the styled parts to the tokens list
                tokens.append((list_style.get('tag', ''), tag_formatted))
                tokens.append((next_style, next_formatted))
                tokens.append((spread_style, spread_formatted))
                tokens.append((last_style, last_formatted))
                tokens.append((name_style, tracker_name))
            elif banner_regex.match(line):
                # use tracker style to avoid the highlight or list style to apply the highlight
                tokens.append((tracker_style.get('banner', ''), line))
                # tokens.append((list_style.get('banner', ''), line))
            else:
                tokens.append((list_style.get('default', ''), line))
            # logger.debug(f"tokens: {tokens}")
            return tokens

        return get_line_tokens

    @staticmethod
    def _parse_date(date_str):
        return datetime.strptime(date_str, "%y-%m-%d")


def format_statustime(obj, freq: int = 0):
    width = shutil.get_terminal_size()[0]
    ampm = True
    dayfirst = False
    yearfirst = True
    seconds = int(obj.strftime('%S'))
    dots = ' ' + (seconds // freq) * '.' if freq > 0 else ''
    month = obj.strftime('%b')
    day = obj.strftime('%-d')
    hourminutes = (
        obj.strftime(' %-I:%M%p').rstrip('M').lower()
        if ampm
        else obj.strftime(' %H:%M')
    ) + dots
    if width < 25:
        weekday = ''
        monthday = ''
    elif width < 30:
        weekday = f' {obj.strftime("%a")}'
        monthday = ''
    else:
        weekday = f'{obj.strftime("%a")}'
        monthday = f' {day} {month}' if dayfirst else f' {month} {day}'
    return f' {weekday}{monthday}{hourminutes}'

# Define the style
style = Style.from_dict({
    'menu-bar': f'bg:#396060 {NAMED_COLORS["White"]}',
    'display-area': f'bg:#1d3030 {NAMED_COLORS["White"]}',
    'input-area': f'bg:#1d3030 {NAMED_COLORS["Gold"]}',
    'message-window': f'bg:#1d3030 {NAMED_COLORS["LimeGreen"]}',
    'status-window': f'bg:#396060 {NAMED_COLORS["White"]}',
})

def check_alarms():
    """Periodic task to check alarms."""
    today = (datetime.now()-timedelta(days=1)).strftime("%y-%m-%d")
    while True:
        f = freq  # Interval (e.g., 6, 12, 30, 60 seconds)
        s = int(datetime.now().second)
        n = s % f
        w = f if n == 0 else f - n
        time.sleep(w)  # Wait for the next interval
        ct = datetime.now()
        current_time = format_statustime(ct, freq)
        message = f"{current_time}"
        update_status(message)
        newday = ct.strftime("%y-%m-%d")
        if newday != today:
            logger.info(f"new day: {newday}")
            today = newday
            cleanup_old_logs()
            rotate_backups(trf_home, logger)

def start_periodic_checks():
    """Start the periodic check for alarms in a separate thread."""
    threading.Thread(target=check_alarms, daemon=True).start()

def center_text(text, width: int = shutil.get_terminal_size()[0] - 2):
    if len(text) >= width:
        return text
    total_padding = width - len(text)
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding
    return ' ' * left_padding + text + ' ' * right_padding


dialog_visible = [False]
message_visible = [False]

selected_id = None

# Tracker mapping example
# UI Components
menu_text = "menu  a)dd d)elete e)dit i)nfo l)ist r)ecord s)how ^q)uit"
menu_container = Window(content=FormattedTextControl(text=menu_text), height=1, style="class:menu-bar")

search_field = SearchToolbar(
    text_if_not_searching=[
    ('class:not-searching', "Press '/' to start searching.")
    ],
    ignore_case=True,
    )

def update_status(new_message):
    status_control.text = new_message
    app.invalidate()  # Request a UI refresh

tracker_lexer = TrackerLexer()
info_lexer = InfoLexer()
help_lexer = HelpLexer()
default_lexer = DefaultLexer()

display_area = TextArea(
    text="",
    read_only=True,
    search_field=search_field,
    lexer=tracker_lexer,
    focus_on_click=True,
    scrollbar=True
    )

def set_lexer(document_type: str):
    if document_type == 'list':
        display_area.lexer = tracker_lexer
    elif document_type == 'info':
        display_area.lexer = info_lexer
    elif document_type == 'help':
        display_area.lexer = help_lexer
    else:
        display_area.lexer = default_lexer

input_area = TextArea(
    focusable=True,
    multiline=True,
    prompt='> ',
    scrollbar=True,
    height=D(preferred=5, max=10),  # Set preferred and max height
    style="class:input-area"
)

dynamic_input_area = DynamicContainer(lambda: input_area)

input_container = ConditionalContainer(
    content=dynamic_input_area,
    filter=Condition(lambda: dialog_visible[0])
)

# Define the message control and message window
message_control = FormattedTextControl(text="")

def calculate_height():
    message = message_control.text  # Get the current message
    lines = message.count('\n')   # Count lines (including wrapped lines)
    return D(preferred=lines, max=lines+1)

message_window = DynamicContainer(
    lambda: Window(
        content=message_control,
        height=calculate_height(),  # Use dynamic height based on content
        style="class:message-window"
    )
)

message_container = ConditionalContainer(
    content=message_window,
    filter=Condition(lambda: message_visible[0])
)

dialog_area = HSplit(
        [
            message_window,
            HorizontalLine(),
            input_container,
        ]
    )

dialog_container = ConditionalContainer(
    content=dialog_area,
    filter=Condition(lambda: dialog_visible[0])
)

status_control = FormattedTextControl(text=f"{format_statustime(datetime.now(), freq)}")
status_window = Window(content=status_control, height=1, style="class:status-window", width=D(preferred=20), align=WindowAlign.LEFT)

page_control = FormattedTextControl(text="")
page_window = Window(content=page_control, height=1, style="class:status-window", width=D(preferred=20), align=WindowAlign.CENTER)

right_control = FormattedTextControl(text="menu ")
right_window = Window(content=right_control, height=1, style="class:status-window", width=D(preferred=20), align=WindowAlign.RIGHT)


def set_pages(txt: str):
    page_control.text = f"{txt} "


status_area = VSplit(
    [
        status_window,
        page_window,
        right_window
    ],
    height=1,
)

def get_row_col():
    row_number = display_area.document.cursor_position_row
    col_number = display_area.document.cursor_position_col
    return row_number, col_number

def get_page_row():
    row = display_area.document.cursor_position_row
    page = tracker_manager.get_active_page()
    return page, row


def get_tracker_from_row()->int:
    page, row = get_page_row()
    id = tracker_manager.row_to_id.get((page, row), None)
    logger.debug(f"{page = }, {row = } => {id = }")
    if id is not None:
        tracker = tracker_manager.get_tracker_from_id(id)
    else:
        tracker = None
    return tracker

def get_tracker_from_tag(tag: str):
    return tracker_manager.get_tracker_from_tag(tag)

def read_readme():
    try:
        content = None
        with importlib.resources.open_text('trf', 'README.txt') as readme_file:
            content = readme_file.read()
        return content
    except FileNotFoundError:
        return "README.txt file not found."

body = HSplit([
    # menu_container,
    display_area,
    status_area,
    message_container, # Conditional Message Area
    dialog_container,  # Conditional Input Area
    ConditionalContainer(content=search_field, filter=Condition(lambda: is_active_mode('search'))),
])

# Boolean to track the visibility of the float
float_visible = [False]  # Use a list so we can modify it within a closure

def display_float(event):
    # Toggle the visibility flag
    float_visible[0] = not float_visible[0]

    # Force the app to refresh the layout to apply the visibility change
    event.app.invalidate()


screen_width, screen_height = shutil.get_terminal_size()


kb = KeyBindings()

@kb.add('c-q')
def exit_app(*event):
    """Exit the application."""
    app.exit()

def set_float(content: str, title: str):
    # Create a FormattedTextControl to dynamically display the content
    screen_width, screen_height = shutil.get_terminal_size()
    content = content.strip()
    float_lines = [f" {x.rstrip()} " for x in content.split('\n')]
    float_width = max(len(x) for x in float_lines) + 4
    float_height = len(float_lines) + 3
    top = 0 # (screen_height - float_height) // 4
    left = (screen_width - float_width) # // 2

    # Create the floating content and wrap it with a Frame to add a border
    floating_content = Frame(
        body=Window(
            content=FormattedTextControl(
                text="\n".join(float_lines),
                ),
            height=len(float_lines),
            ),
        title=title,
        )
    # Create a ConditionalContainer to control the visibility of the Float
    conditional_floating_content = ConditionalContainer(
        content=floating_content,
        filter=Condition(lambda: float_visible[0])  # Control visibility based on float_visible
    )
    return Float(content=conditional_floating_content, top=top, left=left)


float = None
# @kb.add('c-space')  # Control + Space
# @kb.add('.')  # Control + Space
def toggle_shortcuts(event=None):
    logger.debug(f"toggle_shortcuts: {float_visible = }")
    # Toggle the visibility flag
    float_visible[0] = not float_visible[0]

    # Force the app to refresh the layout to apply the visibility change
    app.invalidate()


def clear_search(*event):
    logger.debug("clear search")
    search_state = get_app().current_search_state
    text = search_state.text
    search_state.text = ''
    cancel(event)

def clear_info(*event):
    set_mode('main')
    logger.debug("clear info")
    list_trackers()

def menu(event=None):
    """Focus menu."""
    if event:
        if app.layout.has_focus(root_container.window):
            focus_previous(event)
        else:
            app.layout.focus(root_container.window)


def sort(event=None):
    set_mode('sort')
    message_control.text = wrap(f" Sort by n)ext, l)ast, m)odified, s)ubject or i)d", 0)
    set_mode('handle_sort')


def sort_by(event=None):
    key = event.key_sequence[0].key
    if key == 'n':
        tracker_manager.sort_by = 'next'
    elif key == 'l':
        tracker_manager.sort_by = 'last'
    elif key == 's':
        tracker_manager.sort_by = 'subject'
    elif key == 'm':
        tracker_manager.sort_by = 'modified'
    elif key == 'i':
        tracker_manager.sort_by = 'id'
    close_dialog(changed=True)


def display_info(msg: str, doc_type: str = 'info'):
    display_message(msg, 'info')
    set_mode('info')


def do_about(*event):
    display_info('about track ...')


def do_commands(*event):
    output = ["Commands"]
    for mode, bindings in mode2bindings.items():
        if mode.startswith('handle'):
            continue
        output.append(f"   {mode}")
        for key, command in bindings.items():
            output.append(f"      {key: <8} {command.__name__}")
    display_info("\n".join(output))

def refresh_info(*event):
    tracker_manager.refresh_info()
    list_trackers()

def next_page(*event):
    logger.debug("next page")
    tracker_manager.next_page()
    list_trackers()

def previous_page(*event):
    logger.debug("previous page")
    tracker_manager.previous_page()
    list_trackers()

def list_trackers(*event):
    """List trackers."""
    set_mode('main')
    display_message(tracker_manager.list_trackers(), 'list')
    logger.debug(f"in list_trackers: {tracker_manager.get_tracker_from_id(tracker_manager.selected_id)= }")
    logger.debug(f"in list_trackers: {tracker_manager.get_row_from_id(tracker_manager.selected_id)= }")
    page, row = tracker_manager.selected_row
    if (page, row) != (None, None):
        logger.debug(f"{page = }, {row = }")
        display_area.buffer.cursor_position = (
            display_area.buffer.document.translate_row_col_to_index(row, 0)
            )
    app.layout.focus(display_area)
    app.invalidate()

def toggle_inspect(*event):
    logger.debug("inspect tracker")
    if mode == 'main':
        tracker = tracker_manager.get_tracker_from_row()
        if not tracker:
            return
        set_mode('inspect')
        display_message(f"{tracker.get_tracker_info()}", 'info')
        app.layout.focus(display_area)
        app.invalidate()
    elif mode == 'inspect':
        list_trackers()


def first_page(*event):
    tracker_manager.first_page()
    list_trackers()

def do_restore_defaults(*event):
    tracker_manager.restore_defaults()
    display_info("Defaults restored.", 'info')

def save_to_clipboard(*event):
    # Access the content of the TextArea
    if display_area.text:
        pyperclip.copy(display_area.text)
        display_info('display copied to system clipboard', 'info')

def do_help(*event):
    help_text = read_readme()
    display_info(wrap(help_text, 0), 'help')


def close_dialog(event=None, changed=False):
    input_area.text = ''
    message_control.text = ''
    if changed:
        list_trackers()
    set_mode('main')
    app.layout.focus(display_area)

def cancel(event=None):
    close_dialog(event, False)

def settings(event=None):
    if mode == 'main':
        message_control.text = "Editing settings. \nPress 'ctrl-s' to save changes or 'escape' to cancel"
        settings_map = tracker_manager.settings
        yaml_string = StringIO()
        # Step 2: Dump the CommentedMap into the StringIO object
        yaml.dump(settings_map, yaml_string)
        # Step 3: Get the string from the StringIO object
        yaml_output = yaml_string.getvalue()
        input_area.text = yaml_output
        app.layout.focus(input_area)
        set_mode('settings')
    elif mode == 'settings':
        yaml_string = input_area.text
        changed = False
        if yaml_string:
            yaml_input = StringIO(yaml_string)
            updated_settings = yaml.load(yaml_input)
            tracker_manager.settings.update(updated_settings)
            transaction.commit()
            tracker_manager.save_data()
            logger.debug(f"updated settings:\n{yaml_string}")
            tracker_manager.refresh_info()
            changed = True
        close_dialog(changed=changed)


def new(event=None):
    if mode == 'main':
        message_control.text = wrap("""\
Enter the subject of the new tracker. Optionally append a comma and the datetime of the first completion, and again, optionally, another comma and the timedelta of the expected interval until the next completion, e.g. 'subject, 3p wed, +7d'.  Press 'enter' to save changes or '^c' to cancel.
    """, 0)
        app.layout.focus(input_area)
        set_mode('new')
    elif mode == 'new':
        name = input_area.text.strip()
        msg = []
        changed = False
        if name:
            parts = [x.strip() for x in name.split(",")]
            name = parts[0] if parts else None
            date = parts[1] if len(parts) > 1 else None
            interval = parts[2] if len(parts) > 2 else None
            if name:
                doc_id = tracker_manager.add_tracker(name)
                changed = True
                logger.debug(f"added tracker: {name}")
            else:
                msg.append("No name provided.")
            if date and not msg:
                dtok, dt = Tracker.parse_dt(date)
                if not dtok:
                    msg.append(dt)
                else:
                    # add an initial completion at dt
                    tracker_manager.record_completion(doc_id, (dt, timedelta(0)))
                    changed = True
            if interval and not msg:
                tdok, td = Tracker.parse_td(interval)
                if not tdok:
                    msg.append(td)
                else:
                    # add a fictitious completion at td before dt
                    tracker_manager.record_completion(doc_id, (dt-td, timedelta(0)))
                    changed = True
            close_dialog(changed=changed)
    else:
        return


def delete(event=None):
    if mode == 'main':
        tracker = tracker_manager.get_tracker_from_row()
        if not tracker:
            return
        set_mode('delete')
        message = f" Delete tracker [{tracker.doc_id}] {tracker.name}?\n Press 'y' to delete or 'n' to cancel.\n"
        message_control.text = wrap(message, 0)
        set_mode('delete')
    elif mode == 'delete':
        key = event.key_sequence[0].key
        logger.debug(f"got key: {key = }")
        changed = False
        if key == 'y':
            tracker_manager.delete_tracker(tracker_manager.selected_id)
            logger.debug(f"deleted tracker: {tracker_manager.selected_id}")
            changed = True
        close_dialog(changed=changed)
    else:
        return


def complete(event=None):
    if mode == 'main':
        tracker = tracker_manager.get_tracker_from_row()
        if not tracker:
            return
        message_control.text = wrap(f'Adding a new completion datetime for [{tracker.doc_id}] {tracker.name}.\nPress "Ctrl-S" to save changes or "escape" to cancel.', 0)
        app.layout.focus(input_area)
        set_mode('complete')
    elif mode == 'complete':
        changed = False
        completion_str = input_area.text.strip()
        ok = False
        if completion_str:
            ok, completion = Tracker.parse_completion(completion_str)
            logger.debug(f"got completion_str: '{completion_str}'; {completion = } for {selected_id}")
            if ok:
                logger.debug(f"recording completion_dt: '{completion}' for {selected_id}")
                tracker_manager.record_completion(tracker_manager.selected_id, completion)
                changed = True
        close_dialog(changed=changed)
    else:
        return


def rename(event=None):
    if mode == 'main':
        tracker = tracker_manager.get_tracker_from_row()
        if not tracker:
            return
        set_mode('rename')
        message_control.text = f'Editing the name for [{tracker.doc_id}]{tracker.name}\nPress "Ctrl-S" to save changes or "escape" to cancel.'
        input_area.text = tracker.name
        app.layout.focus(input_area)
        set_mode('rename')
    elif mode == 'rename':
        changed = False
        name = input_area.text.strip()
        if name:
            logger.debug(f"got name: '{name}' for {selected_id}")
            tracker_manager.rename_tracker(tracker_manager.selected_id, name)
            changed = True
        close_dialog(changed=changed)
    else:
        return

def history(event=None):
    if mode == 'main':
        tracker = tracker_manager.get_tracker_from_row()
        if not tracker:
            return
        set_mode('history')
        message_control.text = wrap(f'Editing the history of completions for [{tracker.doc_id}] {tracker.name}.\nModify, add or remove completions - one per line.\nPress "Ctrl-S" to save changes or "escape" to cancel.', 0)
        # input_area.height = D(preferred=10, max=12)
        input_area.text = tracker.format_history()
        app.layout.focus(input_area)
        set_mode('history')
    elif mode == 'history':
        history = input_area.text.strip()
        selected_id = tracker_manager.selected_id
        if history:
            logger.debug(f"starting history: '{history}' for {selected_id}")
            try:
                ok, completions = tracker_manager.get_tracker_from_id(selected_id).parse_completions(history)
                logger.debug(f"back from parse_completions: {ok = }, {completions = }")
                if ok:
                    logger.debug(f"recording '{completions}' for {selected_id}")
                    tracker_manager.record_completions(
                        tracker_manager.selected_id,
                        completions
                        )
                    close_dialog(changed=True)
                else:
                    display_message(f"Invalid history: '{completions}'", 'error')
            except Exception as e:
                display_message(f"Invalid history: '{history}': {e}", 'error')
        else:
            logger.debug(f"removing all completions for {selected_id}")
            tracker_manager.remove_completions(tracker_manager.selected_id)
            close_dialog(changed=True)
    else:
        return


def move_to_page(event):
    page = event.key_sequence[0].key if event else None
    if not page and page in range(1, 10):
        return
    logger.debug(f"got {page = }, {type(page) = }")

    # tracker_manager.set_active_page(int(page)-1)
    tracker_manager.set_page(int(page)-1)
    list_trackers()


def move_to_tag(event):
    tag = event.key_sequence[0].key if event else None
    logger.debug(f"got {tag = }")
    if not tag:
        return
    row = list(string.ascii_lowercase).index(tag) + 1
    display_area.buffer.cursor_position = (
        display_area.buffer.document.translate_row_col_to_index(row, 0)
    )

def set_mode_bindings():
    page_keys = tuple([str(x) for x in range(1, 10)])
    tag_keys = tuple([x for x in string.ascii_lowercase])
    sort_keys = ('n', 'l', 'm', 's', 'i')
    bool_keys = ('y', 'n')
    mode2bindings = {
        'main': OrderedDict([
            ('.', toggle_shortcuts),
            ('f1', menu),
            ('f2', do_about),
            ('f3', toggle_shortcuts),
            ('f4', settings),
            ('f5', do_help),
            ('S', sort),
            ('N', new),
            ('C', complete),
            ('R', rename),
            ('H', history),
            ('D', delete),
            ('space', toggle_inspect),
            ('left', previous_page),
            ('right', next_page),
            (tag_keys, move_to_tag),
            (page_keys, move_to_page),
            ('c-i', refresh_info),
            ('c-c', save_to_clipboard),
            ('c-q', exit_app),
            ]),
        'inspect': {
            'space': toggle_inspect,
            '.': toggle_shortcuts,
            },
        'sort': {
            sort_keys: sort_by,
            '.': toggle_shortcuts,
            },
        'new': {
            'c-s': new,
            # '.': toggle_shortcuts,
            },
        'delete': {
            bool_keys: delete,
            '.': toggle_shortcuts,
            },
        'complete' : {
            'c-s': complete,
            # '.': toggle_shortcuts,
            },
        'rename' : {
            'c-s': rename,
            # '.': toggle_shortcuts,
            },
        'history' : {
            'c-s': history,
            # '.': toggle_shortcuts,
            },
        'settings': {
            'c-s': settings,
            # '.': toggle_shortcuts,
            },
        'search': {
            'escape': clear_search,
            },
        'info': {
            'escape': clear_info,
            },
        }

    return mode2bindings

mode2bindings = set_mode_bindings()

def log_key_bindings(kb: KeyBindings):
    log_output = []
    for binding in kb.bindings:
        keys = ' + '.join(str(key) for key in binding.keys)
        handler = binding.handler.__name__
        # Check for a filter (condition)
        if binding.filter():
            condition = binding.filter()  # Get the condition/filter applied
            if condition == True:
                log_output.append(f"       keys: {keys}, handler: {handler}, condition: {condition}")
    logger.debug(f"key bindings for {mode}:\n" + '\n'.join(log_output))

def is_active_mode(m: str)-> bool:
    return m == mode


def set_bindings():
    """/
    For each mode, add a binding for each key in mode2bindings[mode] to the corresponding method.
    """
    logger.debug("set bindings")
    log_output = []
    global kb
    for current_mode, bindings in mode2bindings.items():
        for key, method in bindings.items():
            if isinstance(key, tuple):
                for k in key:
                    kb.add(k, filter=Condition(lambda m=current_mode: is_active_mode(m)), eager=True)(method)
            else:
                kb.add(key, filter=Condition(lambda m=current_mode: is_active_mode(m)),eager=True)(method)



    for current_mode in ['new', 'complete', 'rename', 'history', 'handle_sort', 'delete', 'settings']:
        kb.add('escape', filter=Condition(lambda m=current_mode: is_active_mode(m)), eager=True)(cancel)

    # log_key_bindings(kb)


menu_items=[
    MenuItem(
        '☰',
        children=[
            MenuItem('F1 toggle menu', handler=menu),
            MenuItem('F2 about trf', handler=do_about),
            MenuItem('F3 edit settings', handler=settings),
            MenuItem('F4 readme', handler=do_help),
            MenuItem('.  show/hide shortcuts', handler=toggle_shortcuts),
            MenuItem('^q exit', handler=exit_app),

        ]
    ),
    Label(text="task tracker", style="class:menu-title"),
]

# Create a MenuContainer using the custom menu bar
root_container = MenuContainer(
    body=body,
    menu_items=menu_items,
    floats=[]
    )

dialog_visible = [False]
message_visable = [False]

def set_mode(active_mode):
    global dialog_visible, message_visible, float_visible, mode #, root_container
    mode = active_mode
    float_visible[0] = False
    right_control.text = f"{mode} "
    dialog_visible[0] = (
        mode in ['new', 'complete', 'rename', 'history', 'new', 'settings']
        )
    message_visible[0] = (
        mode in ['delete', 'delete', 'sort', 'handle_sort']
        )

    logger.debug(f"setting float for mode {mode}")
    if True: #not mode.startswith('handle'):
        output = []
        for key, command in mode2bindings.get(mode, {}).items():
            if isinstance(key, tuple):
                if len(key) > 2:
                    name = f"{key[0]} {key[1]} … {key[-1]}"
                else:
                    name = " ".join([x for x in key])
                output.append(f"{name: <8} {command.__name__}")

                # output.append(f"{key[0]: <8} {key[1]: <8} {command.__name__}")
            else:
                if key.startswith('f'):
                    continue
                output.append(f"{key: <8} {command.__name__}")
        if len(output) > 0:
            # output.insert(0, f".        close this window")
            float = set_float("\n".join(output), f"{mode} shortcuts")
            logger.debug(f"{len(root_container.floats) = }")
            # NOTE: floats[0] must be for the menu - don't remove it
            while len(root_container.floats) > 1:
                root_container.floats.pop(1)
            logger.debug(f"{len(root_container.floats) = }")
            root_container.floats.append(float)
            logger.debug(f"{len(root_container.floats) = }")
            # floats = [float]
            logger.debug(f"{output = }")
    logger.debug(f"dialog_visible: {dialog_visible}; message_visible: {message_visible}")
    # log_key_bindings(kb)

@kb.add('/', filter=Condition(lambda: mode not in ['new', 'complete', 'rename', 'history', 'settings']))
def search_forward(event):
    # Your custom logic to set search mode
    logger.debug("setting search mode")
    set_mode('search')
    # Now trigger the built-in search
    # Now trigger the built-in search
    start_search(display_area.control)

# @kb.add('?')
@kb.add('?', filter=Condition(lambda: mode not in ['new', 'complete', 'rename', 'history', 'settings']))
def search_backward(event):
    # Your custom logic to set search mode
    logger.debug("setting search mode")
    set_mode('search')
    # Now trigger the built-in search
    # Now trigger the built-in search
    start_search(display_area.control, SearchDirection.BACKWARD)

# # Retain the default behavior by not interfering with the rest
# @kb.add('/', filter=Condition(lambda: True))  # Filter ensures it won't overwrite
# def _(event):
#     # This does nothing, allowing the default search binding to stay active
#     logger.debug("passing through /")
#     pass

set_mode('main')

set_bindings()

status_area = VSplit(
    [
        status_window,
        page_window,
        right_window
    ],
    height=1,
)


def display_message(message: str, document_type: str = 'list'):
    """Log messages to the text area."""
    # logger.debug(f"display_message: {message}; {document_type = }")
    set_lexer(document_type)
    display_area.text = message
    # message_control.text = ""
    app.invalidate()  # Refresh the UI

def display_notice(message: str, seconds: int = 2):
    original_message = display_area.text
    # set_mode('notice')
    # logger.debug(f"display_notice: {message}; {original_message = }, {selected_mode = }, {message_visible = }")
    logger.debug(f"setting display_area.text to {message}")
    display_area.text = message
    # display_message(message, 'info')
    # app.invalidate()  # Refresh the UI
    # logger.debug("starting thread")
    threading.Thread(target=display_message_after_delay, args=(original_message, seconds,)).start()
    # app.invalidate()

def display_message_after_delay(message: str, seconds: int = 2):
    # Sleep for 3 seconds without blocking the main thread
    # logger.debug("about to sleep")
    time.sleep(seconds)
    # logger.debug("back from sleep")
    display_area.text = message
    return True
    # app.invalidate()


@kb.add('c-e')
def add_example_trackers(*event):
    del_example_trackers()
    lm = TextLorem(srange=(2,3))
    import random
    today = datetime.now().replace(microsecond=0,second=0,minute=0,hour=0)
    for i in range(1,49): # create 48 trackers
        name = f"{lm.sentence()[:-1]}"
        doc_id = 1000 + i # make sure id's don't conflict with existing trackers
        tracker = Tracker(name, doc_id)
        # Add the tracker to the trackers dictionary
        tracker_manager.trackers[doc_id] = tracker
        # intervals
        due = today - timedelta(days=random.choice([-5, 0, 5, 10]))
        avg =timedelta(days=random.choice([7, 10, 14]), hours=random.choice([8, 12, 16, 20]))
        mad = avg / random.choice([12, 8, 6])
        if i < 41:
            completions = [due-2*avg, due-avg-mad, due]
        elif i < 44:
            completions = [due-avg-mad, due]
        elif i < 47:
            completions = [due]
        else:
            completions = []

        for comp in completions:
            hours = random.choice([0, 0, 0, 0, 0, 0, 12, 24, 36])
            sign = random.choice([-1, 1])
            if hours != 0:
                orig_comp = comp
                comp = (comp + timedelta(hours=hours), -timedelta(hours=hours)) if sign == 1 else (comp - timedelta(hours=hours), timedelta(hours=hours))
                logger.debug(f"comp: {comp}; orig_comp: {orig_comp}; sign: {sign}; hours: {hours}")
            tracker_manager.trackers[doc_id].record_completion(comp)
        tracker_manager.save_data()
        tracker_manager.trackers[doc_id].compute_info()
    list_trackers()


@kb.add('c-t')
def add_readme_trackers(*event):
    header = """\
# Automatically generated by trf.add_readme_trackers()
# - do not edit here.

other_replacements = {

    }
"""
    del_example_trackers()
    import random
    today = datetime.now().replace(microsecond=0,second=0,minute=0,hour=0)
    names = { # name -> [next days + (before) or - (after) today, num completions]
        'hot  -  tardy < now': [14, 3],
        'warm - timely < now < tardy': [7, 3],
        'cool - early < now < timely': [1, 3],
        'cold - now < early': [-7, 3],
        'two completions': [-7, 2],
        'one completion': [0, 1],
        'zero completions': [0, 0]
        }
    doc_id = 1000
    for name in names.keys(): # create 6 trackers
        doc_id += 1
        tracker = Tracker(name, doc_id)
        # Add the tracker to the trackers dictionary
        tracker_manager.trackers[doc_id] = tracker
        days, completions = names[name]
        # intervals
        due = today - timedelta(days=days)
        avg = timedelta(days=random.choice([6, 7]), hours=random.choice([8, 12, 16, 20]))
        mad = timedelta(days = 1, hours = random.choice([4, 8, 12]))
        if completions == 3:
            completions = [due-2*avg, due-avg-mad, due]
        elif completions == 2:
            completions = [due-avg-mad, due]
        elif completions == 1:
            completions = [due]
        else:
            completions = []

        for comp in completions:
            hours = random.choice([0, 0, 0, 0, 0, 6, 9, 12])
            sign = random.choice([-1, 1])
            if hours != 0:
                orig_comp = comp
                comp = (comp + timedelta(hours=hours), -timedelta(hours=hours)) if sign == 1 else (comp - timedelta(hours=hours), timedelta(hours=hours))
                logger.debug(f"comp: {comp}; orig_comp: {orig_comp}; sign: {sign}; hours: {hours}")
            tracker_manager.trackers[doc_id].record_completion(comp)
        tracker_manager.save_data()
        tracker_manager.trackers[doc_id].compute_info()
    list_trackers()


@kb.add('c-r')
def del_example_trackers(*event):
    remove = []
    for id, tracker in tracker_manager.trackers.items():
        # if tracker.name.startswith('#'):
        if tracker.doc_id >= 1000:
            remove.append(id)
    for id in remove:
        tracker_manager.delete_tracker(id)
    list_trackers()


def set_pages(txt: str):
    page_control.text = f"{txt} "


status_area = VSplit(
    [
        status_window,
        page_window,
        right_window
    ],
    height=1,
)

layout = Layout(root_container)

app = Application(layout=layout, key_bindings=kb, full_screen=True, mouse_support=True, style=style)

app.layout.focus(root_container.body)


def main():
    try:
        logger.info(f"Started TrackerManager with database file {db_path}")
        display_text = tracker_manager.list_trackers()
        display_message(display_text)
        start_periodic_checks()  # Start the periodic checks
        app.run()
    except Exception as e:
        logger.error(f"exception raised:\n{e}")
    else:
        logger.error("exited tracker")
    finally:
        if tracker_manager:
            tracker_manager.close()
            logger.info(f"Closed TrackerManager and database file {db_path}")
        else:
            logger.info("TrackerManager was not initialized")

if __name__ == "__main__":
    main()
