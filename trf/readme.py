# trf/readme.py

readme_template = """\

{tracker}


### Motivation

As an example, consider the task of "filling the bird feeders". Suppose you want to have an idea when you should next fill them. One approach would be to set a reminder to fill them every 14 days starting from the last time you filled them. When the reminder is triggered, you could check the feeders to see if they are empty. If they are, you could fill them and then perhaps adjust the reminder to repeat every 13 days. On the other hand, if they are not yet empty, you might adjust the reminder to repeat every 15 days. Repeating this process, you might eventually set a repetition frequency for the reminder that predicts fairly well the next time you should fill them.

The goal of *trf* is to save you trouble of going through this iterative process. Here's how it works:


1. In *trf*, press "N" to add a new tracker and name it "fill bird feeders".
2. The first time you fill the feeders, press "C" to add a completion, select the "fill bird feeders" tracker and enter the date and time of the completion. This date and time will be added to the history of completions for the "fill bird feeders" tracker.
3. The next time you need to fill the feeders, repeat the process described in step 2. At this point, you will have two datetimes in the history of the tracker, *trf* will calculate the interval between them and set the "expected next completion" by adding the interval to last completion date and time.
4. The process repeats with each completion. There are only two differences when there are more than 2 completions:

      - The "expected next completion" is calculated by adding the *average* of the intervals to the last completion date and time.

      - If there are more than 12 completions, only the last 12 completions are used to calculate the average interval. The estimated next completion date and time is thus based only on the average of the intervals for the most recent 12 completions.

One slight wrinkle when adding a completion is that you might have filled the bird feeders because it was a convenient time even though you estimate that you could have waited another day. In this case the actual interval should be the difference between the last completion date and the current completion date plus one day. On the other hand, you might have noticed that the feeders were empty on the previous day but weren't able to fill them. In this case the actual interval should be the difference between the last completion date and the current completion date minus one day. To accommodate this, when adding a completion you can optionally specify the interval adjustment. E.g., `4p, +1d` would add a completion for 4pm today with an estimate that the completion could have been postponed by one day. Similarly, `4p, -1d` would add a completion for 4pm today with an estimate that the completion should have been done one day earlier.

The recorded history of completions is thus a list of (datetime, timedelta) pairs with a corresponding list of intervals

        history: [(dt[0], td[0]), (dt[1], td[1]), (dt[2], td[2]), ...]
        intervals: [dt[1] + td[1] - dt[0], dt[2] + td[2] - dt[1], ...]

Here is an illustration of the "inspect" display for the "fill bird feeders" tracker showing a history of three completions together with the corresponding two intervals and other related calculations:

{inspect}

Datetimes are reported using 6 digits for the date and 4 digits for the 24-hour time separated by `T`: `yymmddTHHMM`.  Timedeltas are reported as integer numbers of d (days), h (hours) and m (minutes).

Note that the first interval, `+9d11h = 9 days 11 hours`, is the difference between `240829T0600 +1d` and `240820T1900`.  The other intervals are computed in the same way. The `average` interval is just the sum of the two intervals divided by 2. The little upward pointing arrow after the average interval indicates that, since the last interval is greater than the average, the average is decreasing.

The `spread` is the average of the absolute values of the differences between the intervals and the average interval. This *MAD* (mean average deviation) is a standard measure of the spread of a series about its average (mean). These calculations are used in two ways:

1. The `forecast` for when the next completion will be due is the sum of the last `completion` datetime and the `average` interval between completions.
2. The confidence we might have in this forecast depends upon the `spread`. If the `spread` is small, we would expect the actual interval between the last completion and the next completion to be close to the average. Chebyshev's Inequality says, in fact, that the proportion of intervals that lie within `η × spread` of the average interval must be at least `1 - 1/η²`. These are the settings for `early` and `late`:

        early = forecast - η × spread
        late = forecast + η × spread

where the value of η is set by the user. With `η = 3`, e.g., at least 1-1/3^2 ~= 89% of the intervals would put the actual outcome between `early` and `late`. For the bird feeder example:

        early = 240920T0700 - 2 × 1d1h = 240918T0500
        late = 240920T0700 + 2 × 1d1h = 240922T0900

The list view reflects these calculations:

{list}

In this view, the `tag` column presents a convenient way of selecting a tracker for use in another command. E.g., pressing `c`  would move the cursor to the row corresponding to tag `c`. Because only lower-case letters are used for tags, only 26 tags can be displayed on a single page in list view. When there are more than 26 trackers, the list view is divided into multiple pages with the left and right cursor keys used to navigate between pages. An option is to press the integer corresponding to a page number and immediately move the cursor to the first row of that page. Only a single digit can be used with this mechanism but this still allows 9 * 26 = 234 trackers to be quickly selected using at most 2 key presses.

The `forecast` column shows, as mentioned above, the sum of `latest` (the last completion) and the average interval between completions. The `η × spread` column shows the product of `η` and the `spread`, e.g., for the bird feeder example, `η = 2` and `spread = 1d1h` so the column shows `2 × 1d1h = 2d2h`. How good is the forecast? At least 75% of observed intervals would place the actual outcome within `2d2h` of the forecast.

Since it is currently 3:48pm on September 23 or `240923T1548` and this is past `late = 240922T0900`, i.e., more than 2d2h after the forecast for bird feeders, the display shows the bird feeder tracker in a suspiciously-late color, burnt orange. By comparison, `early` and `late` datetimes for "between late and early" are September 23 plus or minus 1 day and 2 hours.  Since the current time lies within this interval, "between early and late" gets an anytime-now color, gold. Finally, since `early` for "before early" is September 29 minus 1 day and 2 hours and this is later than the current time, "before early" gets a not-yet color, blue. There is no forecast for the last two trackers since neither have the two or more completions which are required for an interval on which to base a forecast, so these get trackers get the the no-forecast color, white.

### Usage

#### Installation

This README is available online at [GitHub.io](https://dagraham.github.io/trf-dgraham/). The code itself is available either from [PyPi](https://pypi.org/project/trf-dgraham/) or [GitHub](https://github.com/dagraham/trf-dgraham).

The easiest way to install *trf* is to use either pipx (recommended) or pip at a terminal prompt:

- Using pipx

        > pipx install [--force] trf-dgraham

- Using pip

        > pip install [-U] trf-dgraham

The optional arguments, --force and -U, are used to update an existing installation.

#### Starting *trf*

Once installed you can start *trf* with the following command:

        > trf [log_level] [home_dir] ['restore']

where all three arguments are optional.

- If log_level is given it should be an integer: 10 for debug, 20 for info, 30 for warning or 40 for error. If not given log_level defaults to 20.

- If home_dir is given, it should be the path to the directory for *trf* to use.

    - If home_dir is not given but there is an environmental variable, TRFHOME, that specifies a directory, then that directory will be used as the home directory.

    - Finally, if neither home_dir nor TRFHOME is given, then *trf* will use the current working directory as its home directory.

- If restore is given, then instead of starting *trf*,  an option will be offered to restore the datastore from one of its backup files - more on this below.

The home directory is where the datastore, data backup files and log files are stored.

The datastore used by *trf* is a ZOBD database.  The data itself is a python dictionary with integer doc_id's as keys and dictionaries as values. These dictionaries contain entries for the tracker name and the history of completions and internals for the intervals and other computed values.  An additional dictionary containing user settings is also stored in the ZOBD datastore.

The ZOBD datastore transparently stores these python objects as 'pickled' versions of the objects themselves, using two files called 'track.fs' and 'track.fs.index'. Track keeps a daily, rotating back up of these two files in a zip format when ever 'track.fs' has been modified since the last backup.  Of these zip files, only 7 are kept  including the 3 most recent 3 files and 4 older files separated by intervals of at least 14 days. ZOBD also uses files called 'track.fs.lock' and 'track.fs.tmp' but they are not needed for restoring the datastore and are not backed up.

In addition to the 'backup' subdirectory, *trf* keeps a daily rotating backup of its log files in another subdirectory called 'logs'.

Here is an illustration of home_dir as it might appear on November 9, 2024:

        home_dir
            backup/
                240913.zip
                240928.zip
                241013.zip
                241028.zip
                241106.zip
                241107.zip
                241108.zip
            logs/
                trf.log
                trf241102.log
                trf241103.log
                trf241104.log
                trf241105.log
                trf241106.log
                trf241107.log
                trf241108.log
            trf.fs
            trf.fs.index
            trf.fs.lock
            trf.fs.tmp

If the optional 'restore' were given, then a list of the available backup zip files in the 'backup' sub directory of the home dir would be presented to the user with a prompt to choose the zip file from which to restore the datastore. If the user chooses a zip file, the current 'track.fs' and 'track.fs.index' files would first be saved as 'restore.zip' and then these files would be replaced by the corresponding files from the selected zip file. When next restarted, *trf* would use the restored files.

#### Using *trf*

The menu bar has the following options:

            trf
                F1) toggle menu
                F2) about track
                F3) check for updates
                F4) edit settings
                F5) refresh info
                F6) restore default settings
                F7) copy display to clipboard
                F8) help
                ^q) quit
            view
                i) inspect tracker
                l) list trackers
                s) sort trackers
                t) select row from tag
            edit
                n) create new tracker
                c) add completion
                d) delete tracker
                e) edit history
                r) rename tracker
i
Most options have fairly obvious meanings and can be invoked either from the menu or by pressing the relevant key. E.g., for `sort trackers`, either clicking the menu item or pressing `s` would offer the option to sort the trackers either by f)orecast datetime, l)atest datetime, n)ame or i)d. Just press the relevant key, e.g., `n` to sort by name.

Similarly, when you press `n` to create a new tracker, the one requirement is that you specify a name for the new tracker

        > the name of my tracker

You can, optionally, specify a first completion by appending a comma and a datetime, e.g.,

        > the name of my tracker, 3p

would record a completion for 3pm today. You can also, optionally, provide an estimate for the next completion by appending another comma and a timedelta, e.g.,

        > the name of my tracker, 3p, +12d

would not only record a completion for 3pm today but also provide 12 days as an initial estimate for the interval until the next completion will be needed.

As a final illustration, if you press `i` to inspect a tracker when the cursor is in a row of the list view corresponding to a tracker, details about the tracker will be immediately displayed. However, if a tracker row is not selected, then you will first be prompted to select a tracker by pressing the key corresponding to the tag from the first column of the list view that corresponds to the tracker. E.g., pressing `i` and then `c` at the prompt would show the details of "before early" in the illustration above.

"""

fp = '👣'

# Define replacements for image links or text alternatives
image_replacements = {
    "tracker":  """\
<div style="display: flex; align-items: center;">
  <div style="flex: 1;">
<H1>trf-dgraham</H1>
<b>tracker record and forecast</b> is a simple application for tracking the sequence of occasions on which a task is completed and predicting when the next completion will likely be needed.
  </div>
  <div style="flex: 0; padding-left: 10px; padding-right: 6px;">
    <img src="tracker.png" alt="" style="max-width: 140px;">
  </div>
</div>
""",
    "inspect": "![inspect view](tracker_inspect.png)",
    "list": "![list view](tracker_list.png)",
}

text_replacements = {
    "tracker": """\
                                           +---------------------+
 trf-dgraham                               |           👣        |
 tracker - record and forecast             |          👣         |
 This is a simple application for tracking |            👣       |
 the sequence of occasions on which a task |              👣     |
 is completed and predicting when the next |             👣      |
 completion will likely be needed.         |           👣        |
                                           +---------------------+
        """,
    "inspect": """\
+----------------------------------------------------------------+
|   name:        fill bird feeders                               |
|   doc_id:      1                                               |
|   created:     240915T1232                                     |
|   modified:    240923T1544                                     |
|   completions: (3)                                             |
|      240820T1900 +0m, 240829T0600 +1d, 240909T1900 +0m         |
|   intervals:   (2)                                             |
|      +9d11h, +11d13h                                           |
|      average:  10d12h↑                                         |
|      spread:   1d1h                                            |
|   forecast:    240920T0700                                     |
|      early:    240918T0500                                     |
|      late:     240922T0900                                     |
+----------------------------------------------------------------+
""",
    "list": """\
+----------------------------------------------------------------+
|  tag   forecast  η spread   latest    name                     |
|   a    24-09-20   2d2h     24-09-09   fill bird feeders        |
|   b    24-09-23   1d2h     24-09-13   between early and late   |
|   c    24-09-29   1d2h     24-09-19   before early             |
|   d       ~         ~      24-09-12   only one completion      |
|   e       ~         ~         ~       no completions yet       |
+----------------------------------------------------------------+
"""
}

def generate_readme():
    with open("README.md", "w") as f:
        f.write(readme_template.format(**image_replacements))
    with open("trf/README.txt", "w") as f:
        f.write(readme_template.format(**text_replacements))


if __name__ == "__main__":
    print("generating README.md and README.txt")
    generate_readme()