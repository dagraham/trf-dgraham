from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import Application
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.layout import Layout
from prompt_toolkit.filters import Condition

class Dialog:
    modes = ['menu', 'list', 'inspect', 'boolian', 'select', 'sort']
    def __init__(self):
        self.set_mode('list')

    def set_mode(self, mode):
        # print(f"set_mode: {mode}")
        self.mode = mode


kb = KeyBindings()

menu_keys = [
    'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'c-q',
    'l', 'n'
    ]

# only makes sense if the main, list trackers view is showing
# 'enter' activates 'inspect' if a tracker row is selected
# list_keys = ['enter', 'i', 'c', 'r', 's', 't', 'n', 'space']
list_keys = ['i', 'c', 'r', 's', 't', 'n', 'space']

# 'enter' returns to the main, list trackers view
# inspect_keys = ['enter', 'c', 'r', 'e', 'd', ]
inspect_keys = ['c', 'r', 'e', 'd', ]

select_keys = list(string.ascii_lowercase)
select_keys.append('escape')
for key in select_keys:
    kb.add(key, filter=Condition(lambda: dialog.mode == 'select'), eager=True)(lambda event, key=key: select_tag(event, key))
def select_tag(event, key):
    print(f"key pressed: {key}")

bool_keys = ['y', 'n', 'escape', 'enter']
for key in bool_keys:
    kb.add(key, filter=Condition(lambda: dialog.mode == 'boolian'), eager=True)(lambda event, key=key: select_boolian(event, key))
def select_boolian(event, key):
    print(f"key pressed: {key}")


dialog = Dialog()

@Condition
def is_menu_mode():
    return dialog.mode == 'menu'

@Condition
def is_inspect_mode():
    return dialog.mode == 'inspect'

@kb.add('q')
def _(event):
    print("q pressed - common to all modes")
    app.exit()

# @kb.add('enter', filter=is_menu_mode)
def _(event):
    print(f"Enter pressed in list mode, {dialog.mode = }")
    dialog.set_mode('inspect')
    # print(f"new mode {dialog.mode = }, {dialog.is_inspect() = }")

# @kb.add('enter', filter=is_inspect_mode)
# def _(event):
#     print(f"Enter pressed in inspect mode, {dialog.mode = }")
#     dialog.set_mode('list')
#     # print(f"new mode {dialog.mode = }, {dialog.is_list() = }")

# Example application setup
text_area = TextArea()
layout = Layout(text_area)

# Create the Application instance
app = Application(
    layout=layout,
    key_bindings=kb,  # Start with the list mode bindings
    full_screen=False
)

app.run()
# Create instance of Dialog, passing the app instance
