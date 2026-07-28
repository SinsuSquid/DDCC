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

sys.path.insert(0, os.getcwd())
import parser
from parser import RPYParser, ASTNode

from terminal import (
    IS_TTY,
    set_cbreak,
    restore_cbreak,
    kbhit,
    read_key_safe,
    handle_ctrl_c,
)
from state import (
    CHARACTER_STYLES,
    StateObject,
    ConfigMock,
    PERSISTENT_PATH,
    CHARACTERS_DIR,
    save_persistent_data,
    load_persistent_data,
    interpolate_text,
    eval_condition,
    has_chr_file,
    is_json_serializable,
)
from renpy_mock import RenPyMock
from ui import display_dialogue, select_choice, show_main_menu
from poem_game import play_poem_game, handle_special_poem, display_poem

console = Console()


def load_all_scripts(game_scripts_dir: str):
    label_registry = {}
    parsed_files = {}
    
    for filename in sorted(os.listdir(game_scripts_dir)):
        if filename.endswith(".rpy"):
            filepath = os.path.join(game_scripts_dir, filename)
            root_node = RPYParser().parse_file(filepath)
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
    save_path = os.path.join(os.getcwd(), "savegame.json")
    if not os.path.exists(save_path):
        return False
        
    try:
        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        saved_pt = data.get("persistent_vars", {}).get("playthrough", 0)
        current_pt = getattr(engine.state.get("persistent"), "playthrough", 0)
        sayori_deleted = not has_chr_file("sayori.chr")

        if saved_pt == 0 and (current_pt >= 1 or sayori_deleted):
            console.print("\n[bold red]Error: Save file corrupt or 'sayori.chr' is missing or corrupted.[/bold red]")
            time.sleep(2.0)
            return False

        for k, v in data["state_vars"].items():
            engine.state[k] = v
            
        for k, v in data["persistent_vars"].items():
            setattr(engine.state["persistent"], k, v)
            
        def get_node(fp, line):
            if not fp or not line:
                return None
            filename = os.path.basename(fp)
            root = engine.parsed_files.get(filename)
            if root:
                return find_node_by_line(root, fp, line)
            return None
            
        current_filepath = data["current_filepath"]
        current_line = data["current_line"]
        engine.current_node = get_node(current_filepath, current_line)
        engine.child_index = data["child_index"]
        
        engine.block_stack = []
        for line, idx, fp in data["block_stack"]:
            n = get_node(fp, line)
            if n:
                engine.block_stack.append((n, idx))
                
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
            "clear": [False] * 10,
            "clearall": False,
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
        
        self.state["delete_character"] = self.delete_character
        self.state["restore_all_characters"] = self.restore_all_characters
        self.state["restore_relevant_characters"] = self.restore_relevant_characters
        self.state["pause"] = self.pause
        def fallback_glitchtext(length=20):
            import random
            chars = "¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿĀāĂăĄąĆćĈĉĊċČčĎďĐđĒēĔĕĖėĘęĚěĜĝĞğĠġĢģĤĥĦħĨĩĪīĬĭĮįİıĲĳĴĵĶķĸĹĺĻļĽľĿŀŁłŃńŅņŇňŉŊŋŌōŎŏŐőŒœŔŕŖŗŘřŚśŜŝŞşŠšŢţŤťŦŧŨũŪūŬŭŮůŰűŲųŴŵŶŷŸŹźŻżŽž"
            return "".join(random.choice(chars) for _ in range(length))
        self.state["glitchtext"] = fallback_glitchtext

        for filename, root_node in self.parsed_files.items():
            self.execute_defines(root_node)
            self.execute_init_python_blocks(root_node)

    def execute_init_python_blocks(self, root_node: ASTNode):
        for child in root_node.children:
            if child.node_type == "python_block":
                self.execute_python_block(child)

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
        clean_name = name[:-4] if name.endswith(".chr") else name
        paths = [
            os.path.join(CHARACTERS_DIR, f"{clean_name}.chr"),
            os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", f"{clean_name}.chr"),
            os.path.join(os.getcwd(), "game_scripts", f"{clean_name}.chr")
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        console.print(f"\n[bold red]System: Character file '{clean_name}.chr' deleted.[/]\n")

    def restore_all_characters(self, verbose: bool = False):
        chars = ["sayori.chr", "monika.chr", "natsuki.chr", "yuri.chr"]
        os.makedirs(CHARACTERS_DIR, exist_ok=True)
        for c in chars:
            c_path = os.path.join(CHARACTERS_DIR, c)
            if not os.path.exists(c_path):
                src1 = os.path.join(os.getcwd(), "DDLC-1.1.1-pc", "characters", c)
                src2 = os.path.join(os.getcwd(), "game_scripts", c)
                if os.path.exists(src1):
                    try:
                        with open(src1, "rb") as sf, open(c_path, "wb") as tf:
                            tf.write(sf.read())
                    except Exception:
                        pass
                elif os.path.exists(src2):
                    try:
                        with open(src2, "rb") as sf, open(c_path, "wb") as tf:
                            tf.write(sf.read())
                    except Exception:
                        pass
                else:
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

    def resolve_label_name(self, label_name: str) -> str:
        if label_name.startswith("expression "):
            label_name = label_name[11:].strip()

        if label_name in self.label_registry:
            return label_name

        try:
            eval_res = str(eval(label_name, self.state))
            if eval_res in self.label_registry:
                return eval_res
            elif eval_res.startswith("natsuki_exclusive2_") and "natsuki_exclusive2_1" in self.label_registry:
                return "natsuki_exclusive2_1"
            elif eval_res.startswith("yuri_exclusive2_") and "yuri_exclusive2_1" in self.label_registry:
                return "yuri_exclusive2_1"
            elif eval_res.startswith("natsuki_exclusive_") and "natsuki_exclusive_1" in self.label_registry:
                return "natsuki_exclusive_1"
            elif eval_res.startswith("yuri_exclusive_") and "yuri_exclusive_1" in self.label_registry:
                return "yuri_exclusive_1"
            elif eval_res.startswith("poem_special_"):
                return "poem_special_1"
            else:
                prefix = eval_res.rsplit("_", 1)[0]
                matches = [l for l in self.label_registry if l.startswith(prefix)]
                if matches:
                    return matches[0]
        except Exception:
            pass

        return label_name

    def jump(self, label_name: str):
        resolved = self.resolve_label_name(label_name)

        if resolved in ("ch30_main", "ch40_main", "splashscreen", "yuri_kill_3"):
            self.state["in_yuri_kill"] = False
            self.state["skip_mode"] = False
            self.state["auto_mode"] = False

        if resolved in self.label_registry:
            self.current_node = self.label_registry[resolved]
            self.child_index = 0
            self.block_stack = []
            self.if_chain_satisfied = False
            self.jumped = True
        else:
            raise ValueError(f"Label not found: {label_name}")

    def call(self, label_name: str):
        resolved = self.resolve_label_name(label_name)

        if resolved in ("ch30_main", "ch40_main", "splashscreen", "yuri_kill_3"):
            self.state["in_yuri_kill"] = False
            self.state["skip_mode"] = False
            self.state["auto_mode"] = False

        if resolved == "poem":
            play_poem_game(self.state)
            return

        if resolved in self.label_registry:
            self.call_stack.append((self.current_node, self.child_index, list(self.block_stack)))
            self.current_node = self.label_registry[resolved]
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
            exec(code, self.state, self.state)
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
        persistent_pt = getattr(self.state.get("persistent"), "playthrough", 0)
        if persistent_pt == 3 and not getattr(self.state.get("persistent"), "monika_kill", False):
            if not has_chr_file("monika.chr"):
                cur_label = self.current_node.content.get("name") if self.current_node else ""
                if cur_label not in ("ch30_end", "ch30_clear", "ch40_main"):
                    self.state["persistent"].monika_kill = True
                    self.jump("ch30_end")
                    return

        if node.node_type in ("elif", "else") and self.if_chain_satisfied:
            return
            
        if node.node_type not in ("if", "elif", "else"):
            self.if_chain_satisfied = False

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
                exec(code, self.state, self.state)
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
                self.current_node = None

        if node.node_type not in ("if", "elif", "else"):
            self.if_chain_satisfied = False

        if node.node_type == "if":
            cond = node.content.get("condition", "")
            res = eval_condition(cond, self.state)
            if res:
                self.if_chain_satisfied = True
                self.block_stack.append((self.current_node, self.child_index, True))
                self.current_node = node
                self.child_index = 0
            else:
                self.if_chain_satisfied = False

        elif node.node_type == "elif":
            if self.if_chain_satisfied:
                pass
            else:
                cond = node.content.get("condition", "")
                res = eval_condition(cond, self.state)
                if res:
                    self.if_chain_satisfied = True
                    self.block_stack.append((self.current_node, self.child_index, True))
                    self.current_node = node
                    self.child_index = 0
                else:
                    self.if_chain_satisfied = False

        elif node.node_type == "else":
            if self.if_chain_satisfied:
                pass
            else:
                self.if_chain_satisfied = True
                self.block_stack.append((self.current_node, self.child_index, True))
                self.current_node = node
                self.child_index = 0

        elif node.node_type == "menu":
            selected = select_choice(node, self.state)
            if selected:
                self.block_stack.append((self.current_node, self.child_index))
                self.current_node = selected
                self.child_index = 0

        elif node.node_type == "command":
            self.handle_command(node.content["cmd"], node.content["args"])

        elif node.node_type == "label":
            self.block_stack.append((self.current_node, self.child_index))
            self.current_node = node
            self.child_index = 0

    def run(self):
        try:
            self.init_game()
            
            while True:
                while True:
                    action = show_main_menu()

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
                        import getpass
                        self.init_game()
                        persistent_pt = getattr(self.state.get("persistent"), "playthrough", 0)
                        if persistent_pt == 3:
                            name_input = getpass.getuser()
                        else:
                            name_input = console.input("[bold cyan]Enter player name (default 'MC'): [/]").strip()
                            if not name_input:
                                name_input = "MC"
                        self.state["player"] = name_input
                        time.sleep(1.0)
                        self.jump("start")
                        self.jumped = False
                        break

                while self.current_node:
                    if self.jumped:
                        self.jumped = False
                        continue

                    if self.child_index >= len(self.current_node.children):
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
                            frame = self.block_stack.pop()
                            if len(frame) == 3:
                                self.current_node, self.child_index, self.if_chain_satisfied = frame
                            else:
                                self.current_node, self.child_index = frame
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

                if "persistent" in self.state:
                    save_persistent_data(self.state["persistent"])
                console.print("\n[bold yellow]Returning to Main Menu...[/]\n")
                time.sleep(1.2)
        except KeyboardInterrupt:
            handle_ctrl_c()


if __name__ == "__main__":
    try:
        engine = DDCCEngine(os.path.join(os.getcwd(), "game_scripts"))
        engine.run()
    except KeyboardInterrupt:
        restore_cbreak()
        console.print("\n[bold pink1]Game interrupted. Thanks for visiting the Literature Club! 🎀[/]\n")
        sys.exit(0)
