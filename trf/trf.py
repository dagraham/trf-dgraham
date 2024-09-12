# trf/trf.py
import sys, os
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.layout import Layout
import logging

from . import init_db, close_db, setup_logging
from .backup import backup_to_zip, rotate_backups, restore_from_zip

# this will be set in main() as a global variable
logger = None

# this is a singleton instance initialized in main()
tracker_manager = TrackerManager()

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
    def format_td(cls, td: timedelta, short=False):
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
            ret = ''.join(until[:2]) if short else sign + ''.join(until)
            return ret
        except Exception as e:
            logger.debug(f'{td}: {e}')
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
        logger.debug(f"parse_td: {td}")
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

        logger.debug(f"parts: {dt}, {td}")
        msg = []
        if not dt:
            return False, ""
        dtok, dt = cls.parse_dt(dt)
        if not dtok:
            msg.append(dt)
        if td:
            logger.debug(f"{td = }")
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
        completions = [x.strip() for x in completions.split('; ') if x.strip()]
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
        logger.debug(f"Created tracker {self.name} ({self.doc_id})")


    @property
    def info(self):
        # Lazy initialization with re-computation logic
        if not hasattr(self, '_info') or self._info is None:
            logger.debug(f"Computing info for {self.name} ({self.doc_id})")
            self._info = self.compute_info()
        return self._info

    def compute_info(self):
        # Example computation based on history, returning a dict
        result = {}
        if not self.history:
            result = dict(
                last_completion=None, num_completions=0, num_intervals=0, average_interval=timedelta(minutes=0), last_interval=timedelta(minutes=0), spread=timedelta(minutes=0), next_expected_completion=None,
                early=None, late=None, avg=None
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
            result['late'] = None
            result['avg'] = None
            if result['num_completions'] > 0:
                for i in range(len(self.history)-1):
                    #                      x[i+1]                  y[i+1]               x[i]
                    logger.debug(f"{self.history[i+1]}")
                    result['intervals'].append(self.history[i+1][0] + self.history[i+1][1] - self.history[i][0])
                result['num_intervals'] = len(result['intervals'])
            if result['num_intervals'] > 0:
                # result['last_interval'] = intervals[-1]
                if result['num_intervals'] == 1:
                    result['average_interval'] = result['intervals'][-1]
                else:
                    result['average_interval'] = sum(result['intervals'], timedelta()) / result['num_intervals']
                result['next_expected_completion'] = result['last_completion'][0] + result['average_interval']
                result['early'] = result['next_expected_completion'] - timedelta(days=1)
                result['late'] = result['next_expected_completion'] + timedelta(days=1)
                change = result['intervals'][-1] - result['average_interval']
                direction = "↑" if change > timedelta(0) else "↓" if change < timedelta(0) else "→"
                result['avg'] = f"{Tracker.format_td(result['average_interval'], True)}{direction}"
                logger.debug(f"{result['avg'] = }")
            if result['num_intervals'] >= 2:
                total = timedelta(minutes=0)
                for interval in result['intervals']:
                    if interval < result['average_interval']:
                        total += result['average_interval'] - interval
                    else:
                        total += interval - result['average_interval']
                result['spread'] = total / result['num_intervals']
            if result['num_intervals'] >= 1:
                result['early'] = result['next_expected_completion'] - tracker_manager.settings['η'] * result['spread']
                result['late'] = result['next_expected_completion'] + tracker_manager.settings['η'] * result['spread']

        self._info = result
        self._p_changed = True
        # logger.debug(f"returning {result = }")

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
        return '; '.join(output)

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
        self.name = name
        self.invalidate_info()
        self.modified = datetime.now()
        self._p_changed = True

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


    def edit_history(self):
        if not self.history:
            logger.debug("No history to edit.")
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
                print("Invalid choice.")
                return
            selected_comp = self.history[choice - 1]
            print(f"Selected completion: {self.format_completion(selected_comp)}")

            # Choose what to do with the selected entry
            action = input("Do you want to (d)elete or (r)eplace this entry? ").strip().lower()

            if action == 'd':
                self.history.pop(choice - 1)
                print("Entry deleted.")
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
            print("Invalid input. Please enter a number.")

    def get_tracker_info(self):
        if not hasattr(self, '_info') or self._info is None:
            self._info = self.compute_info()
        logger.debug(f"{self._info = }")
        logger.debug(f"{self._info['avg'] = }")
        # insert a placeholder to prevent date and time from being split across multiple lines when wrapping
        # format_str = f"%y-%m-%d{PLACEHOLDER}%H:%M"
        logger.debug(f"{self.history = }")
        history = [f"{Tracker.format_dt(x[0])} {Tracker.format_td(x[1])}" for x in self.history]
        history = ', '.join(history)
        intervals = [f"{Tracker.format_td(x)}" for x in self._info['intervals']]
        intervals = ', '.join(intervals)
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
    spread:   {Tracker.format_td(self._info['spread'], True)}
 forecast:    {Tracker.format_dt(self._info['next_expected_completion'])}
    early:    {Tracker.format_dt(self._info.get('early', '?'))}
    late:     {Tracker.format_dt(self._info.get('late', '?'))}
""", 0)

class TrackerManager:
    labels = "abcdefghijklmnopqrstuvwxyz"

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TrackerManager, cls).__new__(cls)
            cls._instance.init(*args, **kwargs)
        return cls._instance

    def __init__(self, db, connection, root, transaction) -> None:
        self.db = db
        self.connection = connection
        self.root = root
        self.transaction = transaction
        self.trackers = {}
        self.tag_to_id = {}
        self.row_to_id = {}
        self.tag_to_row = {}
        self.id_to_times = {}
        self.active_page = 0
        self.sort_by = "forecast"
        logger.debug(f"using data from\n  {self.db_path}")
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
            logger.debug(f"Warning: could not load data from '{self.db_path}': {str(e)}")
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
            print(f"Setting '{key}' not found.")

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

        logger.debug(f"Tracker '{name}' added with ID {doc_id}")
        return doc_id


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


    def get_tracker_data(self, doc_id: int = None):
        if doc_id is None:
            logger.debug("data for all trackers:")
            for k, v in self.trackers.items():
                logger.debug(f"   {k:2> }. {v.get_tracker_data()}")
        elif doc_id in self.trackers:
            logger.debug(f"data for tracker {doc_id}:")
            logger.debug(f"   {doc_id:2> }. {self.trackers[doc_id].get_tracker_data()}")

    def sort_key(self, tracker):
        forecast_dt = tracker._info.get('next_expected_completion', None) if hasattr(tracker, '_info') else None
        latest_dt = tracker._info.get('last_completion', None) if hasattr(tracker, '_info') else None
        if self.sort_by == "forecast":
            if forecast_dt:
                return (0, forecast_dt)
            if latest_dt:
                return (1, latest_dt)
            return (2, tracker.doc_id)
        if self.sort_by == "latest":
            if latest_dt:
                return (1, latest_dt)
            if forecast_dt:
                return (2, forecast_dt)
            return (0, tracker.doc_id)
        elif self.sort_by == "name":
            return (0, tracker.name)
        elif self.sort_by == "id":
            return (0, tracker.doc_id)
        else: # forecast
            if forecast_dt:
                return (0, forecast_dt)
            if latest_dt:
                return (1, latest_dt)
            return (2, tracker.doc_id)

    def get_sorted_trackers(self):
        # Extract the list of trackers
        trackers = [v for k, v in self.trackers.items()]
        # Sort the trackers
        return sorted(trackers, key=self.sort_key)

    def list_trackers(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%y-%m-%d")
        # width = shutil.get_terminal_size()[0]
        name_width = shutil.get_terminal_size()[0] - 30
        num_pages = (len(self.trackers) + 25) // 26
        set_pages(page_banner(self.active_page + 1, num_pages))
        banner = f"{ZWNJ} tag   forecast  η spread   latest   name\n"
        rows = []
        count = 0
        start_index = self.active_page * 26
        end_index = start_index + 26
        sorted_trackers = self.get_sorted_trackers()
        sigma = self.settings.get('η', 1)
        for tracker in sorted_trackers[start_index:end_index]:
            parts = [x.strip() for x in tracker.name.split('@')]
            tracker_name = parts[0]
            if len(tracker_name) > name_width:
                tracker_name = tracker_name[:name_width - 1] + "…"
            forecast_dt = tracker._info.get('next_expected_completion', None) if hasattr(tracker, '_info') else None
            early = tracker._info.get('early', '') if hasattr(tracker, '_info') else ''
            late = tracker._info.get('late', '') if hasattr(tracker, '_info') else ''
            spread = tracker._info.get('spread', '') if hasattr(tracker, '_info') else ''
            # spread = f"±{Tracker.format_td(spread)[1:]: <8}" if spread else f"{'~': ^8}"
            spread = f"{Tracker.format_td(sigma*spread)[1:]: <8}" if spread else f"{'~': ^8}"
            if tracker.history:
                latest = tracker.history[-1][0].strftime("%y-%m-%d")
            else:
                latest = "~"
            forecast = forecast_dt.strftime("%y-%m-%d") if forecast_dt else center_text("~", 8)
            avg = tracker._info.get('avg', None) if hasattr(tracker, '_info') else None
            interval = f"{avg: <8}" if avg else f"{'~': ^8}"
            tag = TrackerManager.labels[count]
            self.id_to_times[tracker.doc_id] = (early.strftime("%y-%m-%d") if early else '', late.strftime("%y-%m-%d") if late else '')
            self.tag_to_id[(self.active_page, tag)] = tracker.doc_id
            self.row_to_id[(self.active_page, count+1)] = tracker.doc_id
            self.tag_to_row[(self.active_page, tag)] = count+1
            count += 1
            # rows.append(f" {tag}{" "*4}{forecast}{" "*2}{latest}{" "*2}{interval}{" " * 3}{tracker_name}")
            rows.append(f" {tag}{" "*4}{forecast}{" "*2}{spread}{" "*2}{latest}{" " * 3}{tracker_name}")
        return banner +"\n".join(rows)

    def set_active_page(self, page_num):
        if 0 <= page_num < (len(self.trackers) + 25) // 26:
            self.active_page = page_num
        else:
            logger.debug("Invalid page number.")

    def next_page(self):
        self.set_active_page(self.active_page + 1)

    def previous_page(self):
        self.set_active_page(self.active_page - 1)

    def first_page(self):
        self.set_active_page(0)


    def get_tracker_from_tag(self, tag: str):
        pagetag = (self.active_page, tag)
        if pagetag not in self.tag_to_id:
            return None
        return self.trackers[self.tag_to_id[pagetag]]

    def get_tracker_from_row(self, row: int):
        pagerow = (self.active_page, row)
        if pagerow not in self.row_to_id:
            return None
        return self.trackers[self.row_to_id[pagerow]]

    def save_data(self):
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
            logger.debug(f"No tracker found corresponding to label {label}.")

    def get_tracker_from_id(self, doc_id):
        return self.trackers.get(doc_id, None)

    def close(self):
        # Make sure to commit or abort any ongoing transaction
        print()
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

tag_msg = "Press the key corresponding to the tag of the tracker"
tag_keys = list(string.ascii_lowercase)
tag_keys.append('escape')
bool_keys = ['y', 'n', 'escape', 'enter']

# Application Setup
kb = KeyBindings()

def set_mode(mode: str):
    if mode == 'menu':
        # for selecting menu items with a key press
        menu_mode[0] = True
        select_mode[0] = False
        bool_mode[0] = False
        integer_mode[0] = False
        character_mode[0] = False
        dialog_visible[0] = False
        input_visible[0] = False
    elif mode == 'select':
        # for selecting rows by a lower case letter key press
        menu_mode[0] = False
        select_mode[0] = True
        bool_mode[0] = False
        integer_mode[0] = False
        character_mode[0] = False
        dialog_visible[0] = True
        input_visible[0] = False
    elif mode == 'bool':
        # for selecting y/n with a key press
        menu_mode[0] = False
        select_mode[0] = False
        bool_mode[0] = True
        integer_mode[0] = False
        character_mode[0] = False
        dialog_visible[0] = True
        input_visible[0] = False
    elif mode == 'integer':
        # for selecting an single digit integer with a key press
        menu_mode[0] = False
        select_mode[0] = False
        bool_mode[0] = False
        integer_mode[0] = True
        character_mode[0] = False
        dialog_visible[0] = True
        input_visible[0] = False
    elif mode == 'character':
        # for selecting an single digit integer with a key press
        menu_mode[0] = False
        select_mode[0] = False
        bool_mode[0] = False
        integer_mode[0] = False
        character_mode[0] = True
        dialog_visible[0] = True
        input_visible[0] = False
    elif mode == 'input':
        # for entering text in the input area
        menu_mode[0] = False
        select_mode[0] = False
        bool_mode[0] = False
        integer_mode[0] = False
        character_mode[0] = False
        dialog_visible[0] = True
        input_visible[0] = True

class Dialog:
    def __init__(self, action_type, kb, tracker_manager, message_control, display_area, wrap):
        self.action_type = action_type
        self.kb = kb
        self.menu_mode = menu_mode
        self.select_mode = select_mode
        self.tracker_manager = tracker_manager
        self.message_control = message_control
        self.display_area = display_area
        self.wrap = wrap
        self.app = None  # Initialize without app

    def set_app(self, app):
        self.app = app

    def set_done_keys(self, done_keys: list[str]):
        self.done_keys = done_keys

    def start_dialog(self, event):
        logger.debug(f"starting dialog for action {self.action_type}")
        if self.action_type in [
            "complete", "delete", "edit", "rename", "inspect"
            ]:
            tracker = get_tracker_from_row()
            action[0] = self.action_type
            if tracker:
                self.selected_id = tracker.doc_id
                logger.debug(f"got tracker from row")
                self.set_input_mode(tracker)
            else:
                self.done_keys = tag_keys
                self.message_control.text = self.wrap(f" {tag_msg} you would like to {self.action_type}", 0)
                self.set_select_mode()

        elif self.action_type == "new":  # new tracker
            self.set_input_mode(None)

        elif self.action_type == "settings":
            self.set_input_mode(None)

        elif self.action_type == "sort":
            self.set_sort_mode(None)


    def set_input_mode(self, tracker):
        set_mode('input')
        if self.action_type == "complete":
            self.message_control.text = wrap(f' Enter the new completion datetime for "{tracker.name}" (doc_id {self.selected_id})', 0)
            self.app.layout.focus(input_area)
            input_area.accept_handler = lambda buffer: self.handle_completion()
            self.kb.add('enter')(self.handle_completion)
            self.kb.add('c-c', eager=True)(self.handle_cancel)

        elif self.action_type == "edit":
            self.message_control.text = wrap(f' Edit the completion datetimes for "{tracker.name}" (doc_id {self.selected_id})\n Press "enter" to save changes or "^c" to cancel', 0)
            # put the formatted completions in the input area
            input_area.text = wrap(tracker.format_history(), 0)
            self.app.layout.focus(input_area)
            input_area.accept_handler = lambda buffer: self.handle_history()
            self.kb.add('enter')(self.handle_history)
            self.kb.add('c-c', eager=True)(self.handle_cancel)

        elif self.action_type == "rename":
            self.message_control.text = wrap(f' Edit the name of "{tracker.name}" (doc_id {self.selected_id})\n Press "enter" to save changes or "^c" to cancel', 0)
            # put the formatted completions in the input area
            input_area.text = wrap(tracker.name, 0)
            self.app.layout.focus(input_area)
            input_area.accept_handler = lambda buffer: self.handle_rename()
            self.kb.add('enter')(self.handle_rename)
            self.kb.add('c-c', eager=True)(self.handle_cancel)

        elif self.action_type == "inspect":
            set_mode('menu')
            tracker = tracker_manager.get_tracker_from_id(self.selected_id)
            display_message(tracker.get_tracker_info(), 'info')
            app.layout.focus(display_area)

        elif self.action_type == "settings":
            self.message_control.text = " Edit settings. \nPress 'enter' to save changes or '^c' to cancel"
            settings_map = self.tracker_manager.settings
            yaml_string = StringIO()
            # Step 2: Dump the CommentedMap into the StringIO object
            yaml.dump(settings_map, yaml_string)
            # Step 3: Get the string from the StringIO object
            yaml_output = yaml_string.getvalue()
            input_area.text = yaml_output
            self.app.layout.focus(input_area)
            input_area.accept_handler = lambda buffer: self.handle_settings()
            self.kb.add('enter')(self.handle_settings)
            self.kb.add('escape', eager=True)(self.handle_cancel)

        elif self.action_type == "new":
            self.message_control.text = """\
 Enter the name of the new tracker. Optionally append a comma and the datetime
 of the first completion, and again, optionally, another comma and the timedelta
 of the expected interval until the next completion, e.g. 'name, 3p wed, +7d'.
 Press 'enter' to save changes or '^c' to cancel.
"""
            self.app.layout.focus(input_area)
            input_area.accept_handler = lambda buffer: self.handle_new()
            self.kb.add('enter')(self.handle_new)
            self.kb.add('escape', eager=True)(self.handle_cancel)

        elif self.action_type == "delete":
            self.message_control.text = f'Are you sure you want to delete "{tracker.name}" (doc_id {self.selected_id}) (Y/n)?'
            self.set_bool_mode()

    def set_select_mode(self):
        set_mode('select')
        for key in tag_keys:
            self.kb.add(key, filter=Condition(lambda: self.select_mode[0]), eager=True)(lambda event, key=key: self.handle_key_press(event, key))

    def set_sort_mode(self, event=None):
        set_mode('character')
        self.message_control.text = wrap(f" Sort by f)orecast, l)atest, n)ame or i)d", 0)
        self.set_done_keys(['f', 'l', 'n', 'i', 'escape'])
        for key in self.done_keys:
            self.kb.add(key, filter=Condition(lambda: character_mode[0]), eager=True)(lambda event, key=key: self.handle_sort(event, key))

    def handle_key_press(self, event, key_pressed):
        logger.debug(f"{key_pressed = }")
        if key_pressed in self.done_keys:
            if key_pressed == 'escape':
                set_mode('menu')
                return
            tag = (self.tracker_manager.active_page, key_pressed)
            self.selected_id = self.tracker_manager.tag_to_id.get(tag)
            tracker = self.tracker_manager.get_tracker_from_id(self.selected_id)
            logger.debug(f"got id {self.selected_id} from tag {tag}")
            self.set_input_mode(tracker)

    def set_bool_mode(self):
        set_mode('bool')
        for key in bool_keys:
            self.kb.add(key, filter=Condition(lambda: action[0] == self.action_type), eager=True)(lambda event, key=key: self.handle_bool_press(event, key))

    def handle_bool_press(self, event, key):
        logger.debug(f"got key {key} for {self.action_type} {self.selected_id}")
        if key == 'y' or key == 'enter' and self.action_type == "delete":
            self.tracker_manager.delete_tracker(self.selected_id)
            logger.debug(f"deleted tracker: {self.selected_id}")
        set_mode('menu')
        list_trackers()
        self.app.layout.focus(self.display_area)

    def handle_completion(self, event=None):
        completion_str = input_area.text.strip()
        logger.debug(f"got completion_str: '{completion_str}' for {self.selected_id}")
        if completion_str:
            ok, completion = Tracker.parse_completion(completion_str)
            if ok:
                logger.debug(f"recording completion_dt: '{completion}' for {self.selected_id}")
                self.tracker_manager.record_completion(self.selected_id, completion)
                close_dialog()
        else:
            self.display_area.text = "No completion datetime provided."
        set_mode('menu')
        self.app.layout.focus(self.display_area)

    def handle_history(self, event=None):
        history = input_area.text.strip()
        logger.debug(f"got history: '{history}' for {self.selected_id}")
        if history:
            ok, completions = Tracker.parse_completions(history)
            if ok:
                logger.debug(f"recording '{completions}' for {self.selected_id}")
                self.tracker_manager.record_completions(self.selected_id, completions)
                close_dialog()
            else:
                display_message(f"Invalid history: '{completions}'", 'error')

        else:
            display_message("No completion datetime provided.", 'error')
        set_mode('menu')
        self.app.layout.focus(self.display_area)

    def handle_edit(self, event=None):
        completion_str = input_area.text.strip()
        logger.debug(f"got completion_str: '{completion_str}' for {self.selected_id}")
        if completion_str:
            ok, completions = Tracker.parse_completions(completion_str)
            logger.debug(f"recording completion_dt: '{completion}' for {self.selected_id}")
            self.tracker_manager.record_completions(self.selected_id, completion)
            close_dialog()
        else:
            self.display_area.text = "No completion datetime provided."
        set_mode('menu')
        self.app.layout.focus(self.display_area)


    def handle_rename(self, event=None):
        name_str = input_area.text.strip()
        logger.debug(f"got name_str: '{name_str}' for {self.selected_id}")
        if name_str:
            self.tracker_manager.trackers[self.selected_id].rename(name_str)
            logger.debug(f"recorded new name: '{name_str}' for {self.selected_id}")
            close_dialog()
        else:
            self.display_area.text = "New name not provided."
        set_mode('menu')
        list_trackers()
        self.app.layout.focus(self.display_area)

    def handle_settings(self, event=None):

        yaml_string = input_area.text
        if yaml_string:
            yaml_input = StringIO(yaml_string)
            updated_settings = yaml.load(yaml_input)

            # Step 2: Update the original CommentedMap with the new data
            # This will overwrite only the changed values while keeping the structure.
            self.tracker_manager.settings.update(updated_settings)
            transaction.commit()
            logger.debug(f"updated settings:\n{yaml_string}")
            close_dialog()
        set_mode('menu')
        list_trackers()
        self.app.layout.focus(self.display_area)

    def handle_new(self, event=None):
        name = input_area.text.strip()
        msg = []
        if name:
            parts = [x.strip() for x in name.split(",")]
            name = parts[0] if parts else None
            date = parts[1] if len(parts) > 1 else None
            interval = parts[2] if len(parts) > 2 else None
            if name:
                doc_id = self.tracker_manager.add_tracker(name)
                logger.debug(f"added tracker: {name}")
            else:
                msg.append("No name provided.")
            if date and not msg:
                dtok, dt = Tracker.parse_dt(date)
                if not dtok:
                    msg.append(dt)
                else:
                    # add an initial completion at dt
                    self.tracker_manager.record_completion(doc_id, (dt, timedelta(0)))
            if interval and not msg:
                tdok, td = Tracker.parse_td(interval)
                if not tdok:
                    msg.append(td)
                else:
                    # add a fictitious completion at td before dt
                    self.tracker_manager.record_completion(doc_id, (dt-td, timedelta(0)))
            close_dialog()
        if msg:
            self.display_area.text = "\n".join(msg)
        set_mode('menu')
        list_trackers()
        self.app.layout.focus(self.display_area)

    def handle_sort(self, event=None, key_pressed=None):
        if key_pressed in self.done_keys:
            if key_pressed == 'escape':
                set_mode('menu')
                return
            if key_pressed == 'f':
                self.tracker_manager.sort_by = 'forecast'
            elif key_pressed == 'l':
                self.tracker_manager.sort_by = 'latest'
            elif key_pressed == 'n':
                self.tracker_manager.sort_by = 'name'
            elif key_pressed == 'i':
                self.tracker_manager.sort_by = 'id'
            right_control.text = f"{self.tracker_manager.sort_by} "
            list_trackers()
            self.app.layout.focus(self.display_area)

    def handle_cancel(self, event=None, key_pressed=None):
        if key_pressed == 'escape':
            set_mode('menu')
            return
        close_dialog()

# Dialog usage:
dialog_new = Dialog("new", kb, tracker_manager, message_control, display_area, wrap)
kb.add('n', filter=Condition(lambda: menu_mode[0]))(dialog_new.start_dialog)

dialog_complete = Dialog("complete", kb, tracker_manager, message_control, display_area, wrap)
kb.add('c', filter=Condition(lambda: menu_mode[0]))(dialog_complete.start_dialog)

dialog_edit = Dialog("edit", kb, tracker_manager, message_control, display_area, wrap)
kb.add('e', filter=Condition(lambda: menu_mode[0]))(dialog_edit.start_dialog)

dialog_rename = Dialog("rename", kb, tracker_manager, message_control, display_area, wrap)
kb.add('r', filter=Condition(lambda: menu_mode[0]))(dialog_rename.start_dialog)

dialog_inspect = Dialog("inspect", kb, tracker_manager, message_control, display_area, wrap)
kb.add('i', filter=Condition(lambda: menu_mode[0]))(dialog_inspect.start_dialog)

dialog_settings = Dialog("settings", kb, tracker_manager, message_control, display_area, wrap)
kb.add('f4', filter=Condition(lambda: menu_mode[0]))(dialog_settings.start_dialog)

dialog_delete = Dialog("delete", kb, tracker_manager, message_control, display_area, wrap)
kb.add('d', filter=Condition(lambda: menu_mode[0]))(dialog_delete.start_dialog)

dialog_sort = Dialog("sort", kb, tracker_manager, message_control, display_area, wrap)
kb.add('s', filter=Condition(lambda: menu_mode[0]))(dialog_sort.start_dialog)


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
    global logger

    # Get command-line arguments: Process the command-line arguments to get the database file location
    trf_home, log_level, restore = process_arguments()

    # Set up logging
    logger = setup_logging(trf_home=trf_home, log_level=log_level)

    # Initialize the ZODB database

    db_file = os.path.join(trf_home, "trf.fs")

    db, connection, db_root, transaction = init_db(db_file)

    # initialize the tracker manager as a singleton instance
    TrackerManager(db, connection, root, transaction)

    try:
        # Step 3: Run the prompt_toolkit app
        run_app(db_root)
    finally:
        # Step 4: Close the database connection when the app exits
        close_db(db, connection)

if __name__ == "__main__":
    main()
