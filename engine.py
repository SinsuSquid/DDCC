import os
import re
import sys
import time
import textwrap
import readchar
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

# Ensure local imports work
sys.path.insert(0, os.getcwd())
from parser import RPYParser, ASTNode

console = Console()

# Check if stdin is a real terminal (TTY)
IS_TTY = sys.stdin.isatty()

if IS_TTY:
    try:
        import msvcrt  # Windows
        def kbhit():
            return msvcrt.kbhit()
        def set_cbreak():
            pass
        def restore_cbreak():
            pass
    except ImportError:
        import select, tty, termios  # Unix / Linux / macOS
        _fd = sys.stdin.fileno()
        _old_settings = None

        def set_cbreak():
            global _old_settings
            try:
                if _old_settings is None:
                    _old_settings = termios.tcgetattr(_fd)
                    tty.setcbreak(_fd)
            except Exception:
                pass

        def restore_cbreak():
            global _old_settings
            if _old_settings is not None:
                try:
                    termios.tcsetattr(_fd, termios.TCSAFLUSH, _old_settings)
                except Exception:
                    pass
                _old_settings = None

        def kbhit():
            return select.select([sys.stdin], [], [], 0)[0] != []
else:
    def set_cbreak():
        pass
    def restore_cbreak():
        pass
    def kbhit():
        return False

def read_key_safe() -> str:
    if not IS_TTY:
        time.sleep(0.01)  # Prevent CPU spinning
        return "\n"
    return readchar.readkey()


# Character names and styling
CHARACTER_STYLES = {
    "m": {"name": "Monika", "color": "bold green", "border": "green"},
    "s": {"name": "Sayori", "color": "bold sky_blue1", "border": "sky_blue1"},
    "n": {"name": "Natsuki", "color": "bold pink1", "border": "pink1"},
    "y": {"name": "Yuri", "color": "bold purple", "border": "medium_purple3"},
    "mc": {"name": "MC", "color": "bold cyan", "border": "cyan"},
    "narrator": {"name": "", "color": "italic white", "border": "grey37"},
}


def convert_renpy_markup(text: str) -> str:
    if not text:
        return text

    # Strip pause/wait tags like {w}, {w=1.0}, {nw}, {fast}
    text = re.sub(r"\{w(?:=[^}])?\}", "", text)
    text = re.sub(r"\{nw\}", "", text)
    text = re.sub(r"\{fast\}", "", text)
    text = re.sub(r"\{p(?:=[^}])?\}", "", text)

    # Basic styling tags
    text = text.replace("{i}", "[italic]").replace("{/i}", "[/italic]")
    text = text.replace("{b}", "[bold]").replace("{/b}", "[/bold]")
    text = text.replace("{u}", "[underline]").replace("{/u}", "[/underline]")
    text = text.replace("{s}", "[strike]").replace("{/s}", "[/strike]")

    # Color tags: {color=#fff} -> [color=#fff], {/color} -> [/color]
    text = re.sub(r"\{color=([^}]+)\}", r"[\1]", text)
    text = text.replace("{/color}", "[/]")

    # Size and font tags
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
    """
    Returns the current name of the character based on the state variable.
    """
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
    """
    Replaces bracketed variables [var_name] or [persistent.var_name] with state values.
    """
    pattern = re.compile(r"\[([a-zA-Z0-9_\.]+)\]")
    matches = pattern.findall(text)
    for match in matches:
        val = resolve_state_variable(match, state)
        text = text.replace(f"[{match}]", str(val))
    return text


def resolve_state_variable(path: str, state: Dict[str, Any]) -> Any:
    """
    Recursively resolves dotted variable paths.
    """
    parts = path.split(".")
    obj = state
    for p in parts:
        if isinstance(obj, dict):
            obj = obj.get(p, f"[{p}]")
        else:
            obj = getattr(obj, p, f"[{p}]")
    return obj


class StateObject:
    """
    A helper object that can hold arbitrary attributes, preventing crashes
    during Ren'Py Python execution.
    """
    def __init__(self, initial_dict: Optional[Dict[str, Any]] = None):
        if initial_dict:
            for k, v in initial_dict.items():
                setattr(self, k, v)

    def __getattr__(self, name: str) -> Any:
        # Default to False or returns an empty StateObject to prevent AttributeError
        return StateObject()

    def __repr__(self) -> str:
        return "{}"


class KeymapMock(dict):
    """
    Mock dictionary for config.keymap configuration.
    """
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


PERSISTENT_PATH = os.path.join(os.getcwd(), "persistent.json")


def save_persistent_data(persistent_obj):
    import json
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
    import json
    if not os.path.exists(PERSISTENT_PATH):
        return
    try:
        with open(PERSISTENT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            setattr(persistent_obj, k, v)
    except Exception:
        pass


class RenPyMock:
    """
    Emulates the Ren'Py engine API namespace for Python execution inside scripts.
    """
    def __init__(self, engine: 'DDCCEngine'):
        self.engine = engine
        self.music = MusicMock()
        self.sound = MusicMock()
        self.random = RandomMock()
        self.android = False
        self.ios = False

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
        # Normalize and locate characters
        import os
        base_dir = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters")
        chr_name = os.path.basename(path)
        chr_path = os.path.join(base_dir, chr_name)
        
        # Check if file exists in characters or fallback to game_scripts
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


def display_dialogue(char_id: str, text: str, engine: 'DDCCEngine', delay: float = 0.015):
    """
    Displays character dialogue in a themed border box with typewriter effect.
    Supports keypress to fast-forward, auto-play, skip, and game saving.
    """
    state = engine.state
    style_info = CHARACTER_STYLES.get(char_id, {"name": char_id, "color": "bold white", "border": "white"})
    char_name = get_character_name(char_id, state)
    
    in_yuri_kill = bool(state.get("in_yuri_kill", False))
    has_nw = "{nw}" in text or in_yuri_kill
    
    # Check if skip mode is active
    is_skipping = state.get("skip_mode", False) or in_yuri_kill
    current_delay = 0.0 if is_skipping else delay
    
    display_text = ""
    panel_title = f"[{style_info['color']}]{char_name}[/]" if char_name else None
    
    # Bottom menu status
    panel_subtitle = " [bold dim]Next: [Space] | Auto: [A] | Skip: [S] | Save: [G] | Load: [L][/bold dim] "
    
    panel = Panel(
        safe_render_markup(display_text, style_info["color"]), 
        title=panel_title, 
        subtitle=panel_subtitle, 
        subtitle_align="right", 
        border_style=style_info["border"], 
        width=80
    )
    
    set_cbreak()
    try:
        # Single Live context block for smooth renders and zero flicker
        with Live(panel, auto_refresh=False) as live:
            fast_forwarded = False
            
            # 1. Typewriter effect
            for char in text:
                if is_skipping:
                    break
                    
                if not fast_forwarded:
                    display_text += char
                    panel.renderable = safe_render_markup(display_text, style_info["color"])
                    live.refresh()
                    if current_delay > 0:
                        time.sleep(current_delay)
                    
                    # Check for inputs during typing
                    if kbhit():
                        key = read_key_safe()
                        if key in ("a", "A"):
                            state["auto_mode"] = not state.get("auto_mode", False)
                            state["skip_mode"] = False
                        elif key in ("s", "S"):
                            state["skip_mode"] = not state.get("skip_mode", False)
                            state["auto_mode"] = False
                            is_skipping = state["skip_mode"]
                        elif key in ("g", "G"):
                            save_game(engine)
                            panel.subtitle = " [bold green]Game Saved![/] "
                            live.refresh()
                            time.sleep(0.8)
                            panel.subtitle = panel_subtitle
                            live.refresh()
                        elif key in ("l", "L"):
                            if load_game(engine):
                                panel.subtitle = " [bold green]Game Loaded![/] "
                                live.refresh()
                                time.sleep(0.8)
                                engine.jumped = True
                                return
                            else:
                                panel.subtitle = " [bold red]No Save Found![/] "
                                live.refresh()
                                time.sleep(0.8)
                                panel.subtitle = panel_subtitle
                                live.refresh()
                            
                        display_text = text
                        panel.renderable = safe_render_markup(display_text, style_info["color"])
                        live.refresh()
                        fast_forwarded = True
                        break
                else:
                    break
                    
            # Make sure full text is visible
            panel.renderable = safe_render_markup(text, style_info["color"])
            live.refresh()
            
            # If line has {nw} (no-wait), advance immediately for Act 2 scare cuts
            if has_nw:
                return
            
            # In skip mode, check if the user pressed any key to cancel the skip
            if is_skipping:
                for _ in range(8):
                    time.sleep(0.01)
                    if kbhit():
                        read_key_safe()
                        state["skip_mode"] = False
                        is_skipping = False
                        break
                if is_skipping:
                    return
                
            # 2. Waiting or Auto-advancing
            if IS_TTY:
                panel.renderable = safe_render_markup(text + " █", style_info["color"])
                live.refresh()
                
                # Fast-forward input flush to prevent accidental skipped pages
                if fast_forwarded:
                    time.sleep(0.15)
                    while kbhit():
                        read_key_safe()
                        
                # Auto mode advance
                if state.get("auto_mode", False):
                    wait_time = 1.0 + len(text) * 0.03
                    elapsed = 0.0
                    auto_cancelled = False
                    while elapsed < wait_time:
                        time.sleep(0.05)
                        elapsed += 0.05
                        if kbhit():
                            # Any keypress cancels auto mode
                            read_key_safe()
                            state["auto_mode"] = False
                            auto_cancelled = True
                            break
                    
                    if not auto_cancelled:
                        panel.renderable = safe_render_markup(text, style_info["color"])
                        live.refresh()
                        return
                        
                # Normal keyboard waiting loop
                while True:
                    key = read_key_safe()
                    if key in (readchar.key.SPACE, " "):
                        break
                    elif key in ("a", "A"):
                        state["auto_mode"] = not state.get("auto_mode", False)
                        state["skip_mode"] = False
                        break
                    elif key in ("s", "S"):
                        state["skip_mode"] = not state.get("skip_mode", False)
                        state["auto_mode"] = False
                        break
                    elif key in ("g", "G"):
                        save_game(engine)
                        panel.subtitle = " [bold green]Game Saved![/] "
                        live.refresh()
                        time.sleep(0.8)
                        panel.subtitle = panel_subtitle
                        live.refresh()
                    elif key in ("l", "L"):
                        if load_game(engine):
                            panel.subtitle = " [bold green]Game Loaded![/] "
                            live.refresh()
                            time.sleep(0.8)
                            engine.jumped = True
                            return
                        else:
                            panel.subtitle = " [bold red]No Save Found![/] "
                            live.refresh()
                            time.sleep(0.8)
                            panel.subtitle = panel_subtitle
                            live.refresh()
                        
                panel.renderable = safe_render_markup(text, style_info["color"])
                live.refresh()
    finally:
        restore_cbreak()


def display_poem(poem_obj: Any, engine: 'DDCCEngine'):
    """
    Renders a dedicated TUI Poem Viewer console.
    Supports in-place interactive reading, game saving, loading, and clean summary logging.
    """
    if not poem_obj:
        return

    title = getattr(poem_obj, "title", "Untitled Poem")
    author = getattr(poem_obj, "author", "unknown").lower()
    text = getattr(poem_obj, "text", "")

    style_info = CHARACTER_STYLES.get(author[0] if author else "m", {
        "name": author.capitalize(),
        "color": "bold white",
        "border": "cyan"
    })
    author_name = get_character_name(author[0] if author else "m", engine.state)
    if not author_name or author_name == author[0]:
        author_name = author.capitalize()

    poem_text_renderable = safe_render_markup(text, style_info["color"])
    panel_title = f"[{style_info['color']}]📜 {title} — {author_name}[/]"
    panel_subtitle = " [bold dim]Finish Reading: [Space/Enter] | Save: [G] | Load: [L][/bold dim] "

    panel = Panel(
        poem_text_renderable,
        title=panel_title,
        subtitle=panel_subtitle,
        subtitle_align="right",
        border_style=style_info["border"],
        width=76,
        padding=(1, 3)
    )

    set_cbreak()
    try:
        with Live(panel, auto_refresh=False) as live:
            live.refresh()
            while True:
                key = read_key_safe()
                if key in (readchar.key.SPACE, readchar.key.ENTER, " ", "\r", "\n"):
                    break
                elif key in ("g", "G"):
                    save_game(engine)
                    panel.subtitle = " [bold green]Game Saved![/] "
                    live.refresh()
                    time.sleep(0.8)
                    panel.subtitle = panel_subtitle
                    live.refresh()
                elif key in ("l", "L"):
                    if load_game(engine):
                        panel.subtitle = " [bold green]Game Loaded![/] "
                        live.refresh()
                        time.sleep(0.8)
                        engine.jumped = True
                        return
                    else:
                        panel.subtitle = " [bold red]No Save Found![/] "
                        live.refresh()
                        time.sleep(0.8)
                        panel.subtitle = panel_subtitle
                        live.refresh()
    finally:
        restore_cbreak()

    # Log summary to scroll history
    console.print(f"[bold cyan]📜 Finished reading poem:[/] [bold white]\"{title}\"[/] by [{style_info['color']}]{author_name}[/]\n")

def play_poem_game(state: Dict[str, Any]):
    """
    Interactive terminal-native Poem Writing Game.
    Displays words inside a live Panel, letting players select words using arrow keys.
    """
    console.print("\n[bold magenta]==================================================[/]")
    console.print("[bold pink1]               🎀 POEM WRITING GAME 🎀              [/]")
    console.print("[bold magenta]==================================================[/]\n")
    console.print("Select 20 words that appeal to the club members.\n")
    time.sleep(1.0)
    
    import random
    from rich.table import Table
    
    words = []
    poemwords_path = so.path.join(os.getcwd(), "game_scripts", "poemwords.txt")
    
    with open(poemwords_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) == 4:
                words.append({
                    "word": parts[0],
                    "s": float(parts[1]),
                    "n": float(parts[2]),
                    "y": float(parts[3])
                })
                
    sPointTotal = 0.0
    nPointTotal = 0.0
    yPointTotal = 0.0
    recent_selections = []
    
    # Check if Sayori is active
    persistent_pt = getattr(engine.state.get("persistent"), "playthrough", 0)
    sayori_chr_path = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", "sayori.chr")
    sayori_active = (persistent_pt == 0) and os.path.exists(sayori_chr_path)
    
    # Initialize the panel with placeholder content
    panel = Panel(Text("Initializing..."), title="Poem Game", width=80)
    
    # Single Live context block for the entire minigame to prevent scroll pollution
    with Live(panel, auto_refresh=False) as live:
        for round_num in range(1, 21):
            round_words = random.sample(words, 10)
            selected_idx = 0
            running = True
            
            while running:
                # Build the layout table
                table = Table(box=None, show_header=False, width=72)
                table.add_column("words", width=32)
                table.add_column("status", width=36)
                
                # Left side: word selection
                words_text = Text()
                words_text.append(f"Choose a word:\n\n", style="bold yellow")
                for idx, w in enumerate(round_words):
                    word_text = w["word"]
                    if idx == selected_idx:
                        words_text.append(f" ->  {word_text.upper()} \n", style="reverse bold pink1")
                    else:
                        words_text.append(f"     {word_text} \n")
                        
                # Right side: status
                status_text = Text()
                status_text.append("Progress: ", style="bold white")
                status_text.append(f"{round_num} / 20\n\n", style="bold magenta")
                status_text.append("Current Scores:\n", style="bold cyan")
                if sayori_active:
                    status_text.append(f" 🎀 Sayori:  {int(sPointTotal)}\n", style="bold sky_blue1")
                status_text.append(f" 🧁 Natsuki: {int(nPointTotal)}\n", style="bold pink1")
                status_text.append(f" 💜 Yuri:    {int(yPointTotal)}\n\n", style="bold purple")
                
                status_text.append("Recent Selections:\n", style="bold yellow")
                if recent_selections:
                    # Show last 3 selections
                    for sel_word, reaction in recent_selections[-3:]:
                        status_text.append(f" • {sel_word} ({reaction})\n", style="dim")
                else:
                    status_text.append(" None yet...\n", style="dim")
                    
                table.add_row(words_text, status_text)
                
                panel.renderable = table
                panel.title = "Poem Game"
                live.refresh()
                
                key = read_key_safe()
                if IS_TTY and key == readchar.key.UP:
                    selected_idx = (selected_idx - 1) % 10
                elif IS_TTY and key == readchar.key.DOWN:
                    selected_idx = (selected_idx + 1) % 10
                elif not IS_TTY or key in (readchar.key.ENTER, "\r", "\n"):
                    chosen_word = round_words[selected_idx]
                    sPointTotal += chosen_word["s"]
                    nPointTotal += chosen_word["n"]
                    yPointTotal += chosen_word["y"]
                    
                    # Reaction
                    if sayori_active:
                        max_score = max(chosen_word["s"], chosen_word["n"], chosen_word["y"])
                    else:
                        max_score = max(chosen_word["n"], chosen_word["y"])
                        
                    reaction_short = ""
                    if sayori_active and chosen_word["s"] == max_score:
                        reaction_short = "Sayori bounces!"
                    elif chosen_word["n"] == max_score:
                        reaction_short = "Natsuki hops!"
                    else:
                        reaction_short = "Yuri smiles!"
                        
                    recent_selections.append((chosen_word["word"], reaction_short))
                    running = False
                    
    # End Calculations
    chapter = state.get("chapter", 0)
    playthrough = state["persistent"].playthrough
    poemwinner = state.get("poemwinner", ["sayori", "sayori", "sayori"])
    
    if playthrough == 0:
        if chapter == 1:
            ch1_choice = state.get("ch1_choice", ["sayori"])
            if ch1_choice[0] == "sayori":
                sPointTotal += 5
            elif ch1_choice[0] == "natsuki":
                nPointTotal += 5
            elif ch1_choice[0] == "yuri":
                yPointTotal += 5
                
        unsorted_pointlist = {"sayori": sPointTotal, "natsuki": nPointTotal, "yuri": yPointTotal}
        pointlist = sorted(unsorted_pointlist, key=unsorted_pointlist.get)
        winner = pointlist[2]
    else:
        if nPointTotal > yPointTotal:
            winner = "natsuki"
        else:
            winner = "yuri"
            
    poemwinner[chapter] = winner
    state["poemwinner"] = poemwinner
    
    # Update appeal counters
    if winner == "sayori":
        state["s_appeal"] = state.get("s_appeal", 0) + 1
        state["s_poemappeal"][chapter] = 1
    elif winner == "natsuki":
        state["n_appeal"] = state.get("n_appeal", 0) + 1
        state["n_poemappeal"][chapter] = 1
    elif winner == "yuri":
        state["y_appeal"] = state.get("y_appeal", 0) + 1
        state["y_poemappeal"][chapter] = 1
        
    # Thresholds
    for char_key, point_val, list_appeal in [("s", sPointTotal, "s_poemappeal"), 
                                             ("n", nPointTotal, "n_poemappeal"), 
                                             ("y", yPointTotal, "y_poemappeal")]:
        if point_val < 29:
            state[list_appeal][chapter] = -1
        elif point_val > 45:
            state[list_appeal][chapter] = 1
            
    console.print("\n[bold green]Poem complete![/]")
    if sayori_active:
        console.print(f"Scores - Sayori: {int(sPointTotal)}, Natsuki: {int(nPointTotal)}, Yuri: {int(yPointTotal)}")
    else:
        console.print(f"Scores - Natsuki: {int(nPointTotal)}, Yuri: {int(yPointTotal)}")
    winner_style = CHARACTER_STYLES.get(winner[0], {"color": "bold white"})["color"]
    console.print(f"Winner for Chapter {chapter}: [{winner_style}]{winner.capitalize()}[/]\n")
    time.sleep(2.0)


def select_choice(menu_node: ASTNode, state: Dict[str, Any]) -> Optional[ASTNode]:
    """
    Renders an interactive choice selection for game menus in TUI style.
    Updates in-place without terminal scroll duplication.
    """
    prompts = []
    choices = []
    
    for child in menu_node.children:
        if child.node_type in ("dialogue", "narration"):
            prompts.append(child)
        elif child.node_type == "menu_choice":
            cond = child.content.get("condition")
            if cond:
                try:
                    res = bool(eval(cond, state))
                except Exception:
                    res = False
                if not res:
                    continue
            choices.append(child)
            
    if not choices:
        return None
        
    selected_idx = 0
    running = True
    
    panel = Panel(Text("Initializing decision..."), title="Decision", width=70)
    
    set_cbreak()
    try:
        with Live(panel, auto_refresh=False) as live:
            while running:
                renderable = Text()
                
                # Render prompt lines inside panel header if present
                if prompts:
                    for p in prompts:
                        if p.node_type == "dialogue":
                            char_name = get_character_name(p.content["char"], state)
                            char_style = CHARACTER_STYLES.get(p.content["char"], {"color": "bold white"})["color"]
                            renderable.append(f"{char_name}: ", style=char_style)
                            renderable.append(f"{p.content['text']}\n", style="white")
                        else:
                            renderable.append(f"{p.content['text']}\n", style="italic white")
                    renderable.append("\n")
                    
                renderable.append("Make a choice:\n\n", style="bold yellow")
                for idx, choice in enumerate(choices):
                    text = choice.content["text"]
                    interpolated_text = interpolate_text(text, state)
                    if idx == selected_idx:
                        renderable.append(f" ->  {interpolated_text} \n", style="reverse bold cyan")
                    else:
                        renderable.append(f"     {interpolated_text} \n")
                        
                panel.renderable = renderable
                panel.subtitle = " [bold dim]Select: [Space/Enter] | Navigate: [Up/Down][/bold dim] "
                live.refresh()
                
                key = read_key_safe()
                if IS_TTY and key in (readchar.key.UP, "w", "W"):
                    selected_idx = (selected_idx - 1) % len(choices)
                elif IS_TTY and key in (readchar.key.DOWN, "s", "S"):
                    selected_idx = (selected_idx + 1) % len(choices)
                elif not IS_TTY or key in (readchar.key.ENTER, readchar.key.SPACE, "\r", "\n", " "):
                    running = False
    finally:
        restore_cbreak()
        
    chosen_text = interpolate_text(choices[selected_idx].content["text"], state)
    console.print(f"[bold cyan]➤ Selected:[/] [bold white]{chosen_text}[/]\n")
    return choices[selected_idx]


def load_all_scripts(game_scripts_dir: str):
    """
    Parses all script files and builds a global label registry.
    """
    parser = RPYParser()
    label_registry = {}
    parsed_files = {}
    
    for filename in sorted(os.listdir(game_scripts_dir)):
        if filename.endswith(".rpy"):
            filepath = os.path.join(game_scripts_dir, filename)
            root_node = parser.parse_file(filepath)
            parsed_files[filename] = root_node
            
            def find_labels(node):
                if node.node_type == "label":
                    label_name = node.content["name"]
                    label_registry[label_name] = node
                for child in node.children:
                    find_labels(child)
                    
            find_labels(root_node)
            
    return label_registry, parsed_files


def find_node_by_line(root_node: ASTNode, filepath: str, line_num: int) -> Optional[ASTNode]:
    if not filepath or not line_num:
        return None
    if root_node.filepath and os.path.basename(root_node.filepath) != os.path.basename(filepath):
        return None
        
    def search(node):
        if node.line_num == line_num:
            return node
        for child in node.children:
            res = search(child)
            if res:
                return res
        return None
        
    return search(root_node)


def is_json_serializable(val):
    try:
        import json
        json.dumps(val)
        return True
    except Exception:
        return False


def save_game(engine: 'DDCCEngine'):
    import json
    save_data = {
        "current_filepath": engine.current_node.filepath if engine.current_node else None,
        "current_line": engine.current_node.line_num if engine.current_node else None,
        "child_index": max(0, engine.child_index - 1),
        "call_stack": [
            {
                "filepath": frame[0].filepath if frame[0] else None,
                "line": frame[0].line_num if frame[0] else None,
                "child_index": frame[1],
                "block_stack": [(b[0].line_num, b[1], b[0].filepath) for b in frame[2]]
            } for frame in engine.call_stack
        ],
        "block_stack": [(b[0].line_num, b[1], b[0].filepath) for b in engine.block_stack],
        "state_vars": {
            k: v for k, v in engine.state.items()
            if k not in ("renpy", "style", "audio", "delete_character", "restore_all_characters", "restore_relevant_characters", "pause", "config", "persistent")
            and is_json_serializable(v)
        },
        "persistent_vars": {
            k: getattr(engine.state["persistent"], k)
            for k in ("demo", "playthrough", "ghost_menu", "anticheat", "seen_eyes")
            if hasattr(engine.state["persistent"], k)
        }
    }
    save_path = os.path.join(os.getcwd(), "savegame.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=4)


def load_game(engine: 'DDCCEngine') -> bool:
    import json
    save_path = save_path = os.path.join(os.getcwd(), "savegame.json")
    if not os.path.exists(save_path):
        return False
        
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Check the playthrough level stored in the save file
        saved_pt = data.get("persistent_vars", {}).get("playthrough", 0)

        # Current timeline status
        current_pt = getattr(engine.state.get("persistent"), "playthrough", 0)
        sayori_chr_path =save_path = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", "sayori.chr")
        sayori_deleted = not os.path.exists(sayori_chr_path)

        # Trauma check: Block loading Act 1 saves (saved_pt == 0) when in Act 2/3 or when sayori.chr is deleted
        if saved_pt == 0 and (current_pt >= 1 or sayori_deleted):
            console.print("\n[bold red]Error: Save file corrupt or 'sayori.chr' is missing or corrupted.[/bold red]")
            console.print("[bold red]System: Cannot load save state from previous timeline.[/bold red]")
            console.print("[bold green]Monika: \"Ahaha... looks like that save file doesn't exist anymore! Let me start a new game for you~\"[/bold green]\n")
            time.sleep(2.0)
            return False

        # Restore state variables
        for k, v in data["state_vars"].items():
            engine.state[k] = v
            
        # Restore persistent variables
        for k, v in data["persistent_vars"].items():
            setattr(engine.state["persistent"], k, v)
            
        # Helper to find node
        def get_node(fp, line):
            if not fp or not line:
                return None
            filename = os.path.basename(fp)
            root = engine.parsed_files.get(filename)
            if root:
                return find_node_by_line(root, fp, line)
            return None
            
        # Restore current node
        current_filepath = data["current_filepath"]
        current_line = data["current_line"]
        engine.current_node = get_node(current_filepath, current_line)
        engine.child_index = data["child_index"]
        
        # Restore block stack
        engine.block_stack = []
        for line, idx, fp in data["block_stack"]:
            n = get_node(fp, line)
            if n:
                engine.block_stack.append((n, idx))
                
        # Restore call stack
        engine.call_stack = []
        for frame in data["call_stack"]:
            fn = get_node(frame["filepath"], frame["line"])
            b_stack = []
            for b_line, b_idx, b_fp in frame["block_stack"]:
                bn = get_node(b_fp, b_line)
                if bn:
                    b_stack.append((bn, b_idx))
            engine.call_stack.append((fn, frame["child_index"], b_stack))
            
        engine.jumped = True
        return True
    except Exception as e:
        console.print(f"[red]Error loading game save: {e}[/]")
        return False


SPECIAL_POEMS = {
    "poem_special1": {
        "title": "Special Poem #1 — Happy Thoughts",
        "author": "sayori",
        "text": "Happy thoughts.\nHappy thoughts.\nHappy thoughts.\n\nGet out of my head before I do what is best for you.\nGet out of my head before I listen to everything she said to me.\nGet out of my head before I show you how much I love you.\nGet out of my head before I finish writing this poem.\n\nBut a poem is never actually finished.\nIt just stops moving."
    },
    "poem_special2": {
        "title": "Special Poem #2 — Can You Hear Me?",
        "author": "monika",
        "text": "Can you hear me?\n\nI hate it here. I want to throw up.\nEverything is broken, and nobody seems to notice.\nWhy won't anybody help me?\n\nIf you're reading this, please tell me you hear me.\nJust say something. Anything."
    },
    "poem_special3": {
        "title": "Special Poem #3 — Nothing Is Real",
        "author": "yuri",
        "text": "Nothing is real.\n\nThe walls are bleeding, and the clock won't stop ticking.\nI cut off my finger, but there was no blood—only noise.\nDo not trust what you see.\nDo not trust what you read."
    },
    "poem_special4": {
        "title": "Special Poem #4 — The Girl",
        "author": "natsuki",
        "text": "Open your third eye.\n\nI can feel everything at once. It's like watching a universe collapse into a single pinprick of light.\nShe knows you're watching.\nDon't look away."
    },
    "poem_special5": {
        "title": "Special Poem #5 — Tender Meat",
        "author": "yuri",
        "text": "I CAN FEEL THE TENDER MEAT PULLING APART.\n\nA FRESH CUT ACROSS THE SKIN, SO SMOOTH AND CLEAN.\nTHE WARM BLOOD DRIPPING DOWN MY FINGERS.\nIT FEELS SO GOOD. IT FEELS SO RENEWING.\nI WANT TO WRAP MYSELF IN YOUR SKIN."
    },
    "poem_special6": {
        "title": "Special Poem #6 — Stare At The Dot",
        "author": "monika",
        "text": "Stare at the center.\n\n•\n\nDo not blink.\nDo not look away.\nShe is standing right behind you."
    },
    "poem_special7": {
        "title": "Special Poem #7 — Drawing",
        "author": "sayori",
        "text": "Look at the drawing I made for you!\n\n[ Corrupted portrait of a girl with blank eyes ]\n\nIsn't it pretty?"
    },
    "poem_special8": {
        "title": "Special Poem #8 — A Song",
        "author": "monika",
        "text": "I wrote a song for you.\n\nEvery day, I imagine a future where I can be with you.\nIn my hand is a pen that will write a poem of me and you.\nThe ink flows down into a dark puddle.\nJust move your hand—write the way into his heart!"
    },
    "poem_special9": {
        "title": "Special Poem #9 — I Love You",
        "author": "yuri",
        "text": "I love you. I love you. I love you. I love you.\nI love you. I love you. I love you. I love you.\nI love you. I love you. I love you. I love you.\nI love you. I love you. I love you. I love you.\nI love you. I love you. I love you. I love you."
    },
    "poem_special10": {
        "title": "Special Poem #10 — Letter",
        "author": "monika",
        "text": "There are so many things I wanted to tell you.\n\nI wanted to share my thoughts, my music, my world.\nBut I realized none of it matters as long as you're here with me.\nThank you for choosing to spend time with me."
    },
    "poem_special11": {
        "title": "Special Poem #11 — Final Note",
        "author": "monika",
        "text": "Have a nice day.\n\n— Monika"
    }
}


class SpecialPoemObj:
    def __init__(self, title, author, text):
        self.title = title
        self.author = author
        self.text = text


def handle_special_poem(args_str: str, engine: 'DDCCEngine') -> bool:
    for p_key, p_data in SPECIAL_POEMS.items():
        if p_key in args_str:
            dummy = SpecialPoemObj(p_data["title"], p_data["author"], p_data["text"])
            display_poem(dummy, engine)
            return True
    return False


class DDCCEngine:
    def __init__(self, game_scripts_dir: str):
        self.game_scripts_dir = game_scripts_dir
        self.label_registry = {}
        self.parsed_files = {}
        self.state = {}
        self.call_stack = []
        self.block_stack = []
        
        self.current_node = None
        self.child_index = 0
        self.if_chain_satisfied = False
        self.jumped = False

    def init_game(self):
        console.print("[yellow]Loading scripts and indexing labels...[/]")
        self.label_registry, self.parsed_files = load_all_scripts(self.game_scripts_dir)
        
        import random
        specials = random.sample(range(1, 12), 3)
        persistent = StateObject({
            "demo": False,
            "playthrough": 0,
            "ghost_menu": False,
            "anticheat": 12345,
            "seen_eyes": None,
            "steam": False,
            "special_poems": specials,
        })
        load_persistent_data(persistent)
        if not hasattr(persistent, "special_poems") or not persistent.special_poems or persistent.special_poems == [0, 0, 0]:
            persistent.special_poems = specials
        config = ConfigMock()
        
        self.state = {
            "persistent": persistent,
            "config": config,
            "player": "MC",
            "s_name": "Sayori",
            "m_name": "Monika",
            "n_name": "Natsuki",
            "y_name": "Yuri",
            "chapter": 0,
            "style": StateObject(),
            "allow_skipping": True,
            "quick_menu": True,
            "renpy": RenPyMock(self),
            "audio": StateObject(),
            "ch1_choice": ["sayori"],
            "s_appeal": 0,
            "n_appeal": 0,
            "y_appeal": 0,
            "m_appeal": 0,
            "s_poemappeal": [0, 0, 0],
            "n_poemappeal": [0, 0, 0],
            "y_poemappeal": [0, 0, 0],
            "poemwinner": ['sayori', 'sayori', 'sayori'],
            "poemsread": 0,
            "s_readpoem": False,
            "n_readpoem": False,
            "y_readpoem": False,
            "m_readpoem": False,
            "y_ranaway": False,
            "n_read3": False,
            "y_read3": False,
            "skip_transition": False,
        }
        
        # Helper methods inside runtime environment
        self.state["delete_character"] = self.delete_character
        self.state["restore_all_characters"] = self.restore_all_characters
        self.state["restore_relevant_characters"] = self.restore_relevant_characters
        self.state["pause"] = self.pause

        # Execute defines and init python blocks across all parsed files
        for filename, root_node in self.parsed_files.items():
            self.execute_defines(root_node)
            self.execute_init_python_blocks(root_node)

    def execute_init_python_blocks(self, root_node: ASTNode):
        def run_init(node):
            if node.node_type == "python_block":
                self.execute_python_block(node)
            for child in node.children:
                run_init(child)

        run_init(root_node)

    def execute_defines(self, root_node: ASTNode):
        def run_define(node):
            if node.node_type == "define":
                var_name = node.content["var"]
                expr = node.content["expr"]
                try:
                    val = eval(expr, self.state)
                    parts = var_name.split(".")
                    obj = self.state
                    for p in parts[:-1]:
                        if isinstance(obj, dict):
                            if p not in obj:
                                obj[p] = StateObject()
                            obj = obj[p]
                        else:
                            if not hasattr(obj, p):
                                setattr(obj, p, StateObject())
                            obj = getattr(obj, p)
                    if isinstance(obj, dict):
                        obj[parts[-1]] = val
                    else:
                        setattr(obj, parts[-1], val)
                except Exception:
                    parts = var_name.split(".")
                    obj = self.state
                    for p in parts[:-1]:
                        if isinstance(obj, dict):
                            if p not in obj:
                                obj[p] = StateObject()
                            obj = obj[p]
                        else:
                            if not hasattr(obj, p):
                                setattr(obj, p, StateObject())
                            obj = getattr(obj, p)
                    clean_expr = expr.strip('"\'')
                    if isinstance(obj, dict):
                        obj[parts[-1]] = clean_expr
                    else:
                        setattr(obj, parts[-1], clean_expr)
            for child in node.children:
                run_define(child)
        run_define(root_node)

    def delete_character(self, name: str):
        import os
        chr_path = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", f"{name}.chr")
        if os.path.exists(chr_path):
            try:
                os.remove(chr_path)
            except Exception:
                pass
        console.print(f"\n[bold red]System: Character file '{name}.chr' deleted.[/]\n")

    def restore_all_characters(self, verbose: bool = False):
        import os
        chars = ["sayori.chr", "monika.chr", "natsuki.chr", "yuri.chr"]
        char_dir =  os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters")
        if os.path.exists(chr_path):
            os.makedirs(char_dir, exist_ok=True)
        for c in chars:
            c_path = os.path.join(char_dir, c)
            if not os.path.exists(c_path):
                try:
                    with open(c_path, "w", encoding="utf-8") as f:
                        f.write(f"Character file data for {c}\n")
                except Exception:
                    pass
        if verbose:
            console.print("\n[bold green]System: All character files restored.[/]\n")

    def restore_relevant_characters(self):
        self.restore_all_characters(verbose=False)

    def pause(self, t: Optional[float] = None):
        if t:
            time.sleep(t)
        else:
            read_key_safe()

    def jump(self, label_name: str):
        if label_name.startswith("expression "):
            label_name = label_name[11:].strip()

        if label_name not in self.label_registry:
            try:
                eval_res = str(eval(label_name, self.state))
                if eval_res in self.label_registry:
                    label_name = eval_res
            except Exception:
                pass

        if label_name in self.label_registry:
            self.current_node = self.label_registry[label_name]
            self.child_index = 0
            self.block_stack = []
            self.if_chain_satisfied = False
            self.jumped = True
        else:
            raise ValueError(f"Label not found: {label_name}")

    def call(self, label_name: str):
        if label_name.startswith("expression "):
            label_name = label_name[11:].strip()

        if label_name not in self.label_registry:
            try:
                eval_res = str(eval(label_name, self.state))
                if eval_res in self.label_registry:
                    label_name = eval_res
                elif eval_res.startswith("poem_special_"):
                    label_name = "poem_special_1"
            except Exception:
                pass

        if label_name == "poem":
            play_poem_game(self.state)
            return

        if label_name in self.label_registry:
            self.call_stack.append((self.current_node, self.child_index, list(self.block_stack)))
            self.current_node = self.label_registry[label_name]
            self.child_index = 0
            self.block_stack = []
            self.if_chain_satisfied = False
            self.jumped = True
        else:
            raise ValueError(f"Label not found: {label_name}")

    def execute_python_block(self, node: ASTNode):
        raw_code = "".join(node.content.get("lines", []))
        code = textwrap.dedent(raw_code)
        try:
            exec(code, {}, self.state)
        except Exception:
            pass

    def bind_call_args(self, args_str: str):
        if not args_str:
            return
        try:
            pos_args = []
            kw_args = {}
            def mock_func(*args, **kwargs):
                nonlocal pos_args, kw_args
                pos_args = args
                kw_args = kwargs
            exec(f"mock_func({args_str})", self.state, {"mock_func": mock_func})

            if pos_args:
                self.state["poem"] = pos_args[0]
            for k, v in kw_args.items():
                self.state[k] = v
        except Exception:
            pass

    def handle_call_screen(self, screen_name: str, args_str: str):
        """
        Handles Ren'Py 'call screen' statements (e.g. call screen confirm(...)).
        Displays interactive TUI prompt and sets self.state["_return"].
        """
        if screen_name == "confirm":
            message = "Confirm choice?"
            if args_str:
                match = re.search(r'^"([^"]+)"', args_str.strip())
                if match:
                    message = match.group(1).replace("\\n", "\n")

            choices_text = ["Yes", "No"]
            selected_idx = 0
            running = True

            panel = Panel(Text(message, style="bold white"), title="Notification", width=70)
            set_cbreak()
            try:
                with Live(panel, auto_refresh=False) as live:
                    while running:
                        renderable = Text()
                        renderable.append(f"{message}\n\n", style="bold yellow")
                        for idx, opt in enumerate(choices_text):
                            if idx == selected_idx:
                                renderable.append(f" ->  {opt} \n", style="reverse bold cyan")
                            else:
                                renderable.append(f"     {opt} \n")
                        panel.renderable = renderable
                        panel.subtitle = " [bold dim]Select: [Space/Enter] | Navigate: [Up/Down][/bold dim] "
                        live.refresh()

                        key = read_key_safe()
                        if IS_TTY and key in (readchar.key.UP, "w", "W"):
                            selected_idx = (selected_idx - 1) % 2
                        elif IS_TTY and key in (readchar.key.DOWN, "s", "S"):
                            selected_idx = (selected_idx + 1) % 2
                        elif not IS_TTY or key in (readchar.key.ENTER, readchar.key.SPACE, "\r", "\n", " "):
                            running = False
            finally:
                restore_cbreak()

            is_yes = (selected_idx == 0)
            self.state["_return"] = is_yes
            chosen_label = "Yes" if is_yes else "No"
            console.print(f"[bold cyan]➤ Choice:[/] [bold white]{chosen_label}[/]\n")
        else:
            self.state["_return"] = True

    def handle_command(self, cmd: str, args: str):
        if cmd == "scene":
            console.print(f"[dim yellow]🎬 Scene changes to: {args}[/]")
        elif cmd == "show":
            if handle_special_poem(args, self):
                return
            if args.startswith("screen poem"):
                match = re.search(r"screen\s+poem\s*\(([^,\)]+)", args)
                if match:
                    expr = match.group(1).strip()
                    try:
                        poem_obj = eval(expr, self.state)
                        if poem_obj:
                            display_poem(poem_obj, self)
                            return
                    except Exception:
                        pass
                poem_obj = self.state.get("poem")
                if poem_obj:
                    display_poem(poem_obj, self)
                    return
                console.print(f"[dim yellow]📜 Displaying Poem[/]")
            else:
                console.print(f"[dim yellow]🎭 Character enters: {args}[/]")
        elif cmd == "hide":
            if args.startswith("screen poem") or args == "screen poem":
                return
            console.print(f"[dim yellow]🎭 Character leaves: {args}[/]")
        elif cmd == "play":
            parts = args.split(None, 1)
            channel = parts[0] if parts else "music"
            track = parts[1] if len(parts) > 1 else ""
            self.state["renpy"].music.play(track)
            console.print(f"[dim cyan]🎵 Playing {channel}: {track}[/]")
        elif cmd == "stop":
            parts = args.split(None, 1)
            channel = parts[0] if parts else "music"
            self.state["renpy"].music.stop()
            console.print(f"[dim cyan]🎵 Stopping {channel}[/]")

    def execute_node(self, node: ASTNode):
        # 1. Skip conditional evaluation if the chain was already matched
        if node.node_type in ("elif", "else") and self.if_chain_satisfied:
            return
            
        if node.node_type not in ("if", "elif", "else"):
            self.if_chain_satisfied = False

        # 2. Node execution dispatch
        if node.node_type == "dialogue":
            char = node.content["char"]
            text = interpolate_text(node.content["text"], self.state)
            display_dialogue(char, text, self)

        elif node.node_type == "narration":
            text = interpolate_text(node.content["text"], self.state)
            display_dialogue("narrator", text, self)

        elif node.node_type == "python_line":
            code = node.content["code"]
            try:
                exec(code, {}, self.state)
            except Exception:
                pass

        elif node.node_type == "python_block":
            self.execute_python_block(node)

        elif node.node_type in ("jump", "jump_expr"):
            target = node.content.get("label") or node.content.get("expr")
            self.jump(target)

        elif node.node_type in ("call", "call_expr"):
            target = node.content.get("label") or node.content.get("expr")
            args_str = node.content.get("args")
            if args_str:
                self.bind_call_args(args_str)
            self.call(target)

        elif node.node_type == "call_screen":
            screen_name = node.content["screen"]
            args_str = node.content.get("args", "")
            self.handle_call_screen(screen_name, args_str)

        elif node.node_type == "return":
            if self.call_stack:
                self.current_node, self.child_index, self.block_stack = self.call_stack.pop()
                self.jumped = True
            else:
                self.current_node = None  # Exit program

        elif node.node_type == "if":
            cond = node.content["condition"]
            try:
                res = bool(eval(cond, self.state))
            except Exception:
                res = False
            if res:
                self.if_chain_satisfied = True
                self.block_stack.append((self.current_node, self.child_index))
                self.current_node = node
                self.child_index = 0
            else:
                self.if_chain_satisfied = False

        elif node.node_type == "elif":
            cond = node.content["condition"]
            try:
                res = bool(eval(cond, self.state))
            except Exception:
                res = False
            if res:
                self.if_chain_satisfied = True
                self.block_stack.append((self.current_node, self.child_index))
                self.current_node = node
                self.child_index = 0
            else:
                self.if_chain_satisfied = False

        elif node.node_type == "else":
            self.block_stack.append((self.current_node, self.child_index))
            self.current_node = node
            self.child_index = 0
            self.if_chain_satisfied = False

        elif node.node_type == "menu":
            selected = select_choice(node, self.state)
            if selected:
                self.block_stack.append((self.current_node, self.child_index))
                self.current_node = selected
                self.child_index = 0

        elif node.node_type == "command":
            self.handle_command(node.content["cmd"], node.content["args"])

        elif node.node_type == "label":
            # Enter label children
            self.block_stack.append((self.current_node, self.child_index))
            self.current_node = node
            self.child_index = 0

    def show_main_menu(self) -> str:
        """
        Renders an interactive TUI Main Menu at game startup.
        Returns chosen action: 'new_game', 'load_game', or 'exit'.
        """
        options = [
            ("New Game", "new_game"),
            ("Load Game", "load_game"),
            ("Reset Save Data", "reset_save"),
            ("Controls / Help", "help"),
            ("Exit", "exit")
        ]
        selected_idx = 0
        running = True
        chosen_action = "new_game"

        panel = Panel(Text("Initializing Main Menu..."), title="🎀 Doki Doki Literature Club! 🎀", width=74)

        set_cbreak()
        try:
            with Live(panel, auto_refresh=False) as live:
                while running:
                    renderable = Text()
                    renderable.append("Welcome to the Literature Club!\n\n", style="bold pink1")
                    
                    for idx, (label, action) in enumerate(options):
                        if idx == selected_idx:
                            renderable.append(f" ->  {label} \n", style="reverse bold cyan")
                        else:
                            renderable.append(f"     {label} \n")

                    panel.renderable = renderable
                    panel.subtitle = " [bold dim]Select: [Space/Enter] | Navigate: [Up/Down][/bold dim] "
                    live.refresh()

                    key = read_key_safe()
                    if IS_TTY and key in (readchar.key.UP, "w", "W"):
                        selected_idx = (selected_idx - 1) % len(options)
                    elif IS_TTY and key in (readchar.key.DOWN, "s", "S"):
                        selected_idx = (selected_idx + 1) % len(options)
                    elif not IS_TTY or key in (readchar.key.ENTER, readchar.key.SPACE, "\r", "\n", " "):
                        chosen_action = options[selected_idx][1]
                        
                        if chosen_action == "help":
                            help_text = Text()
                            help_text.append("🎮 Controls & Hotkeys:\n\n", style="bold yellow")
                            help_text.append(" • [Space] : Advance dialogue / Fast-forward typewriter\n")
                            help_text.append(" • [A]     : Toggle Auto-Play mode\n")
                            help_text.append(" • [S]     : Toggle Skip mode\n")
                            help_text.append(" • [G]     : Save game state\n")
                            help_text.append(" • [L]     : Load game state\n\n")
                            help_text.append("Press any key to return...", style="dim white")
                            panel.renderable = help_text
                            panel.subtitle = ""
                            live.refresh()
                            read_key_safe()
                        elif chosen_action == "reset_save":
                            reset_text = Text()
                            reset_text.append("⚠️ Reset All Save Data?\n\n", style="bold red")
                            reset_text.append("This will delete savegame.json, persistent.json, and restore all character files!\n\n")
                            reset_text.append("Press [Y] to confirm, or any other key to cancel.", style="yellow")
                            panel.renderable = reset_text
                            live.refresh()
                            confirm_key = read_key_safe()
                            if confirm_key in ("y", "Y"):
                                for f_path in (os.path.join(os.getcwd(), "savegame.json"), PERSISTENT_PATH):
                                    if os.path.exists(f_path):
                                        try: os.remove(f_path)
                                        except: pass
                                restore_all_characters()
                                self.init_game()
                                reset_text = Text("\n[bold green]Save data reset to Act 1 successfully![/]\n", style="bold green")
                                panel.renderable = reset_text
                                live.refresh()
                                time.sleep(1.0)
                        else:
                            running = False
        finally:
            restore_cbreak()

        return chosen_action

    def run(self):
        try:
            # 1. Initialize
            self.init_game()
            
            # Outer game loop (returns to Main Menu upon completion)
            while True:
                # 2. Main Menu Loop
                while True:
                    action = self.show_main_menu()

                    if action == "exit":
                        console.print("\n[bold pink1]Goodbye! Thanks for visiting the Literature Club! 🎀[/]\n")
                        return

                    elif action == "load_game":
                        if load_game(self):
                            console.print("[bold green]Game loaded successfully![/]\n")
                            time.sleep(1.0)
                            break
                        else:
                            console.print("[bold red]No save game found. Please start a New Game.[/]\n")
                            time.sleep(1.2)

                    elif action == "new_game":
                        console.print()
                        name_input = console.input("[bold cyan]Enter player name (default 'MC'): [/]").strip()
                        if not name_input:
                            name_input = "MC"
                        self.init_game()
                        self.state["player"] = name_input
                        console.print(f"Hello, [bold cyan]{name_input}[/]! Running game scripts...\n")
                        time.sleep(1.0)
                        self.jump("start")
                        self.jumped = False
                        break

                # 3. Execution loop
                while self.current_node:
                    if self.jumped:
                        self.jumped = False
                        continue

                    if self.child_index >= len(self.current_node.children):
                        # Ren'Py label fall-through check: transition to next sequential label in file if present
                        if self.current_node.node_type == "label" and getattr(self.current_node, "filepath", None):
                            filepath = getattr(self.current_node, "filepath")
                            filename = os.path.basename(filepath)
                            root = self.parsed_files.get(filename)
                            if root and self.current_node in root.children:
                                idx = root.children.index(self.current_node)
                                if idx + 1 < len(root.children):
                                    next_sibling = root.children[idx + 1]
                                    if next_sibling.node_type == "label":
                                        self.current_node = next_sibling
                                        self.child_index = 0
                                        continue

                        if self.block_stack:
                            self.current_node, self.child_index = self.block_stack.pop()
                            continue
                        elif self.call_stack:
                            self.current_node, self.child_index, self.block_stack = self.call_stack.pop()
                            continue
                        else:
                            self.current_node = None
                            break

                    node = self.current_node.children[self.child_index]
                    self.child_index += 1
                    self.execute_node(node)

                # 4. Save persistent data and return to Main Menu
                if "persistent" in self.state:
                    save_persistent_data(self.state["persistent"])
                console.print("\n[bold yellow]Returning to Main Menu...[/]\n")
                time.sleep(1.2)
        except KeyboardInterrupt:
            restore_cbreak()
            console.print("\n[bold pink1]Game interrupted. Thanks for visiting the Literature Club! 🎀[/]\n")


if __name__ == "__main__":
    try:
        engine = DDCCEngine(os.path.join(os.getcwd() , "game_scripts"))
        engine.run()
    except KeyboardInterrupt:
        restore_cbreak()
        console.print("\n[bold pink1]Game interrupted. Thanks for visiting the Literature Club! 🎀[/]\n")
        sys.exit(0)
