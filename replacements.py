# Define replacements
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
 trf-dgraham                                      +--------------+
                                                  |      👣      |
 tracker - record and forecast                    |     👣       |
 This is a simple application for tracking        |       👣     |
 the sequence of occasions on which a task        |         👣   |
 is completed and predicting when the next        |        👣    |
 completion will likely be needed.                |      👣      |
                                                  +--------------+
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
