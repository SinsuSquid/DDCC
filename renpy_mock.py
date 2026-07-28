import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import Any
from rich.console import Console

from state import MusicMock, RandomMock, save_persistent_data

console = Console()


class RenPyMock:
    """
    Emulates the Ren'Py engine API namespace for Python execution inside scripts.
    """
    def __init__(self, engine: Any):
        self.engine = engine
        self.music = MusicMock()
        self.sound = MusicMock()
        self.random = RandomMock()
        self.android = False
        self.ios = False
        self.windows = True
        self.mac = False
        self.linux = True

    def display_menu(self, items, interact=True, screen='choice'):
        if not interact:
            return None
        valid_choices = [item for item in items if len(item) >= 2 and item[1]]
        if not valid_choices:
            return None
        console.print()
        for idx, (label, cond) in enumerate(valid_choices, 1):
            console.print(f"  [bold cyan][{idx}][/] {label}")
        console.print()
        while True:
            sel = console.input("[bold pink1]Choose an option: [/]").strip()
            if sel.isdigit():
                val = int(sel)
                if 1 <= val <= len(valid_choices):
                    return valid_choices[val - 1][0]

    def pause(self, delay=0):
        if delay and delay > 0:
            time.sleep(delay)

    def full_restart(self, *args, **kwargs):
        self.engine.state["in_yuri_kill"] = False
        self.engine.state["skip_mode"] = False
        self.engine.state["auto_mode"] = False
        self.engine.call_stack.clear()
        self.engine.block_stack.clear()

        playthrough = getattr(self.engine.state.get("persistent"), "playthrough", 0)
        if playthrough == 3:
            self.engine.state["persistent"].autoload = "ch30_main"
            self.engine.jump("ch30_main")
            return
        elif playthrough == 4:
            self.engine.state["persistent"].autoload = "ch40_main"
            self.engine.jump("ch40_main")
            return

        autoload = getattr(self.engine.state.get("persistent"), "autoload", None)
        if autoload and autoload in self.engine.label_registry:
            self.engine.jump(autoload)
        elif "splashscreen" in self.engine.label_registry:
            self.engine.jump("splashscreen")
        else:
            self.engine.jump("start")

    def show(self, *args, **kwargs):
        pass

    def hide(self, *args, **kwargs):
        pass

    def scene(self, *args, **kwargs):
        pass

    def redraw(self, *args, **kwargs):
        pass

    def save_persistent(self, *args, **kwargs):
        if "persistent" in self.engine.state:
            save_persistent_data(self.engine.state["persistent"])

    def list_saved_games(self, *args, **kwargs):
        return []

    def unlink_save(self, *args, **kwargs):
        pass

    def fsencode(self, s):
        return s

    def get_pos(self, *args, **kwargs):
        return 0

    def file(self, path: str):
        base_dir = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters")
        chr_name = os.path.basename(path)
        chr_path = os.path.join(base_dir, chr_name)
        
        if not os.path.exists(chr_path):
            alt_path = os.path.join(os.getcwd(), "game_scripts", chr_name)
            if os.path.exists(alt_path):
                return open(alt_path, "r", encoding="utf-8")
            raise FileNotFoundError(f"Mock RenPy file not found: {path}")
        return open(chr_path, "r", encoding="utf-8")

    def jump(self, label: str):
        self.engine.jump(label)

    def call(self, label: str):
        self.engine.call(label)
