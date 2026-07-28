import os
import sys
import re
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import typing
from typing import Dict, Any, Optional
from rich.console import Console
from rich.text import Text

console = Console()

CHARACTER_STYLES = {
    "m": {"name": "Monika", "color": "bold green", "border": "green"},
    "s": {"name": "Sayori", "color": "bold sky_blue1", "border": "sky_blue1"},
    "n": {"name": "Natsuki", "color": "bold pink1", "border": "pink1"},
    "y": {"name": "Yuri", "color": "bold purple", "border": "medium_purple3"},
    "mc": {"name": "MC", "color": "bold cyan", "border": "cyan"},
    "narrator": {"name": "", "color": "italic white", "border": "grey37"},
}

PERSISTENT_PATH = os.path.join(os.getcwd(), "persistent.json")


class StateObject:
    def __init__(self, initial_dict: Optional[Dict[str, Any]] = None):
        if initial_dict:
            for k, v in initial_dict.items():
                setattr(self, k, v)

    def __getattr__(self, name: str) -> Any:
        return StateObject()

    def __repr__(self) -> str:
        return "{}"


class KeymapMock(dict):
    def __getitem__(self, item):
        if item not in self:
            self[item] = []
        return super().__getitem__(item)


class ConfigMock(StateObject):
    def __init__(self):
        super().__init__()
        self.keymap = KeymapMock()
        self.basedir = os.path.join(os.getcwd(), "DDLC-1.1.1-pc")
        self.allow_skipping = True
        self.developer = False


class MusicMock:
    def __init__(self):
        self.playing = None

    def play(self, music_file, fadeout=1.0, if_changed=True, loop=True, **kwargs):
        self.playing = music_file

    def stop(self, fadeout=1.0, **kwargs):
        self.playing = None

    def get_playing(self, channel='music'):
        return self.playing


class RandomMock:
    def randint(self, a, b):
        import random
        return random.randint(a, b)

    def random(self):
        import random
        return random.random()


def convert_renpy_markup(text: str) -> str:
    if not text:
        return text

    text = re.sub(r"\{w(?:=[^}])?\}", "", text)
    text = re.sub(r"\{nw\}", "", text)
    text = re.sub(r"\{fast\}", "", text)
    text = re.sub(r"\{p(?:=[^}])?\}", "", text)

    text = text.replace("{i}", "[italic]").replace("{/i}", "[/italic]")
    text = text.replace("{b}", "[bold]").replace("{/b}", "[/bold]")
    text = text.replace("{u}", "[underline]").replace("{/u}", "[/underline]")
    text = text.replace("{s}", "[strike]").replace("{/s}", "[/strike]")

    text = re.sub(r"\{color=([^}]+)\}", r"[\1]", text)
    text = text.replace("{/color}", "[/]")

    text = re.sub(r"\{size=[^}]+\}", "", text).replace("{/size}", "")
    text = re.sub(r"\{cps=[^}]+\}", "", text).replace("{/cps}", "")
    text = re.sub(r"\{font=[^}]+\}", "", text).replace("{/font}", "")

    return text


def close_open_rich_tags(s: str) -> str:
    open_tags = []
    tokens = re.finditer(r"\[(/?[a-zA-Z0-9_#]*)\]", s)
    for m in tokens:
        tag = m.group(1)
        if not tag:
            continue
        if tag == "/":
            if open_tags:
                open_tags.pop()
        elif tag.startswith("/"):
            target_tag = tag[1:]
            if target_tag in open_tags:
                open_tags.remove(target_tag)
            elif open_tags:
                open_tags.pop()
        else:
            open_tags.append(tag)
            
    for tag in reversed(open_tags):
        s += f"[/{tag}]"
    return s


def safe_render_markup(raw_text: str, base_style: str = "white") -> Text:
    converted = convert_renpy_markup(raw_text)
    closed = close_open_rich_tags(converted)
    try:
        return Text.from_markup(closed, style=base_style)
    except Exception:
        return Text(raw_text, style=base_style)


def get_character_name(char_id: str, state: Dict[str, Any]) -> str:
    if char_id == "mc":
        return state.get("player", "MC")
    elif char_id == "s":
        return state.get("s_name", "Sayori")
    elif char_id == "m":
        return state.get("m_name", "Monika")
    elif char_id == "n":
        return state.get("n_name", "Natsuki")
    elif char_id == "y":
        return state.get("y_name", "Yuri")
    elif char_id == "narrator":
        return ""
    else:
        return char_id


def interpolate_text(text: str, state: Dict[str, Any]) -> str:
    pattern = re.compile(r"\[([a-zA-Z0-9_\.]+)\]")
    matches = pattern.findall(text)
    for match in matches:
        val = resolve_state_variable(match, state)
        text = text.replace(f"[{match}]", str(val))
    return text


def resolve_state_variable(path: str, state: Dict[str, Any]) -> Any:
    parts = path.split(".")
    obj = state
    for p in parts:
        if isinstance(obj, dict):
            obj = obj.get(p, f"[{p}]")
        else:
            obj = getattr(obj, p, f"[{p}]")
    return obj


def eval_condition(cond: str, state: Dict[str, Any]) -> bool:
    if not cond:
        return False
    cond_clean = cond.strip()
    eval_globals = {
        "True": True,
        "False": False,
        "None": None,
        "len": len,
        "int": int,
        "str": str,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "max": max,
        "min": min,
        "sum": sum,
        "abs": abs,
    }
    eval_globals.update(state)
    try:
        res = eval(cond_clean, eval_globals)
        return bool(res)
    except Exception:
        try:
            val = resolve_state_variable(cond_clean, state)
            if val != f"[{cond_clean}]":
                return bool(val)
        except Exception:
            pass
        return False


CHARACTERS_DIR = os.path.join(os.getcwd(), "characters")


def ensure_characters_dir():
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    for char_name in ("monika.chr", "sayori.chr", "natsuki.chr", "yuri.chr"):
        target = os.path.join(CHARACTERS_DIR, char_name)
        if not os.path.exists(target):
            src1 = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", char_name)
            src2 = os.path.join(os.getcwd(), "game_scripts", char_name)
            if os.path.exists(src1):
                try:
                    with open(src1, "rb") as sf, open(target, "wb") as tf:
                        tf.write(sf.read())
                except Exception:
                    pass
            elif os.path.exists(src2):
                try:
                    with open(src2, "rb") as sf, open(target, "wb") as tf:
                        tf.write(sf.read())
                except Exception:
                    pass
            else:
                try:
                    with open(target, "w", encoding="utf-8") as tf:
                        tf.write(f"Character file for {char_name}")
                except Exception:
                    pass


def has_chr_file(chr_name: str) -> bool:
    ensure_characters_dir()
    path = os.path.join(CHARACTERS_DIR, chr_name)
    return os.path.exists(path)


def delete_chr_file(chr_name: str):
    ensure_characters_dir()
    path = os.path.join(CHARACTERS_DIR, chr_name if chr_name.endswith(".chr") else chr_name + ".chr")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def is_json_serializable(val):
    try:
        json.dumps(val)
        return True
    except Exception:
        return False


def save_persistent_data(persistent_obj):
    data = {}
    for k in ("demo", "playthrough", "ghost_menu", "anticheat", "seen_eyes", "clearall", "first_poem", "first_run", "oldversion", "deleted_saves"):
        if hasattr(persistent_obj, k):
            val = getattr(persistent_obj, k)
            if is_json_serializable(val):
                data[k] = val
    try:
        with open(PERSISTENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def load_persistent_data(persistent_obj):
    if not os.path.exists(PERSISTENT_PATH):
        return
    try:
        with open(PERSISTENT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            setattr(persistent_obj, k, v)
    except Exception:
        pass
