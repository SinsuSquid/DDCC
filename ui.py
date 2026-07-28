import os
import sys
import time
import readchar

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

from terminal import IS_TTY, set_cbreak, restore_cbreak, kbhit, read_key_safe
from state import (
    CHARACTER_STYLES,
    get_character_name,
    interpolate_text,
    safe_render_markup,
    save_persistent_data,
    has_chr_file,
)

console = Console()


def display_dialogue(char_id: str, text: str, engine: Any, delay: float = 0.015):
    """
    Displays character dialogue in a themed border box with typewriter effect.
    Supports keypress to fast-forward, auto-play, skip, and game saving.
    """
    from engine import save_game, load_game

    state = engine.state
    style_info = CHARACTER_STYLES.get(char_id, {"name": char_id, "color": "bold white", "border": "white"})
    char_name = get_character_name(char_id, state)
    
    has_nw = "{nw}" in text
    
    # Check if skip mode is active
    config_obj = state.get("config")
    allow_skipping = getattr(config_obj, "allow_skipping", True) if config_obj else True
    if not allow_skipping:
        state["skip_mode"] = False
        is_skipping = False
    else:
        is_skipping = bool(state.get("skip_mode", False))
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
                            config_obj = state.get("config")
                            allow_skipping = getattr(config_obj, "allow_skipping", True) if config_obj else True
                            persistent_pt = getattr(state.get("persistent"), "playthrough", 0)
                            
                            if not allow_skipping:
                                state["skip_mode"] = False
                                is_skipping = False
                                if persistent_pt == 3:
                                    if not getattr(state.get("persistent"), "tried_skip", False):
                                        state["persistent"].tried_skip = True
                                        engine.jump("ch30_noskip")
                                        engine.jumped = True
                                        return
                                    else:
                                        panel.subtitle = " [bold red]Skipping Disabled![/] "
                                        live.refresh()
                                        time.sleep(0.8)
                                        panel.subtitle = panel_subtitle
                                        live.refresh()
                                else:
                                    panel.subtitle = " [bold red]Skipping Disabled![/] "
                                    live.refresh()
                                    time.sleep(0.8)
                                    panel.subtitle = panel_subtitle
                                    live.refresh()
                            else:
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
            
            # If line has {nw} (no-wait), advance immediately
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
                    persistent_pt = getattr(state.get("persistent"), "playthrough", 0)
                    if persistent_pt == 3 and not getattr(state.get("persistent"), "monika_kill", False):
                        if not has_chr_file("monika.chr"):
                            state["persistent"].monika_kill = True
                            engine.jump("ch30_end")
                            engine.jumped = True
                            return

                    if not IS_TTY:
                        break

                    if not kbhit():
                        time.sleep(0.05)
                        continue

                    key = read_key_safe()
                    if key in (readchar.key.SPACE, " "):
                        break
                    elif key in ("a", "A"):
                        state["auto_mode"] = not state.get("auto_mode", False)
                        state["skip_mode"] = False
                        break
                    elif key in ("s", "S"):
                        config_obj = state.get("config")
                        allow_skipping = getattr(config_obj, "allow_skipping", True) if config_obj else True
                        persistent_pt = getattr(state.get("persistent"), "playthrough", 0)
                        
                        if not allow_skipping:
                            state["skip_mode"] = False
                            if persistent_pt == 3:
                                if not getattr(state.get("persistent"), "tried_skip", False):
                                    state["persistent"].tried_skip = True
                                    engine.jump("ch30_noskip")
                                    engine.jumped = True
                                    return
                                else:
                                    panel.subtitle = " [bold red]Skipping Disabled![/] "
                                    live.refresh()
                                    time.sleep(0.8)
                                    panel.subtitle = panel_subtitle
                                    live.refresh()
                                    continue
                            else:
                                panel.subtitle = " [bold red]Skipping Disabled![/] "
                                live.refresh()
                                time.sleep(0.8)
                                panel.subtitle = panel_subtitle
                                live.refresh()
                                continue
                        else:
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
            else:
                # In non-TTY environment, wait for user input
                try:
                    import sys
                    sys.stdin.readline()
                except Exception:
                    time.sleep(1.5)
    finally:
        restore_cbreak()


def select_choice(menu_node: Any, state: Dict[str, Any]) -> Optional[Any]:
    """
    Renders an interactive TUI decision box using Rich Live.
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
                            renderable.append(f"{interpolate_text(p.content['text'], state)}\n", style="white")
                        else:
                            renderable.append(f"{interpolate_text(p.content['text'], state)}\n", style="italic white")
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
                    return choices[selected_idx]
    finally:
        restore_cbreak()


def show_main_menu() -> str:
    """
    Renders an interactive TUI Main Menu at game startup.
    Returns chosen action: 'new_game', 'load_game', or 'exit'.
    """
    options = [
        ("New Game", "new_game"),
        ("Load Game", "load_game"),
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
                    else:
                        running = False
    finally:
        restore_cbreak()

    return chosen_action
