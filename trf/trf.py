# trf/trf.py
import sys, os
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.layout import Layout
import logging

from . import init_db, close_db, setup_logging


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

    # def __init__(self, db_path=None) -> None:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        if db_path is None:
            db_path = os.path.join(os.getcwd(), "tracker.fs")
        self.db_path = db_path
        self.trackers = {}
        self.tag_to_id = {}
        self.row_to_id = {}
        self.tag_to_row = {}
        self.id_to_times = {}
        self.active_page = 0
        self.storage = FileStorage.FileStorage(self.db_path)
        self.db = DB(self.storage)
        self.connection = self.db.open()
        self.root = self.connection.root()
        self.sort_by = "forecast"  # default sort order, also "latest", "name"
        logger.debug(f"using data from\n  {self.db_path}")
        self.load_data()

    def load_data(self):
        try:
            if 'settings' not in self.root:
                self.root['settings'] = settings_map
                transaction.commit()
            self.settings = self.root['settings']
            if 'trackers' not in self.root:
                self.root['trackers'] = {}
                self.root['next_id'] = 1  # Initialize the ID counter
                transaction.commit()
            self.trackers = self.root['trackers']
        except Exception as e:
            logger.debug(f"Warning: could not load data from '{self.db_path}': {str(e)}")
            self.trackers = {}

    def restore_defaults(self):
        self.root['settings'] = settings_map
        self.settings = self.root['settings']
        transaction.commit()
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
            transaction.commit()
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
        transaction.commit()

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
                transaction.abort()
            else:
                logger.info("Transaction committed.")
                transaction.commit()
        except Exception as e:
            logger.error(f"Error during transaction handling: {e}")
            transaction.abort()
        else:
            logger.info("Transaction handled successfully.")
        finally:
            self.connection.close()


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
