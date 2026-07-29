import os
import sys
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live

from terminal import IS_TTY, set_cbreak, restore_cbreak, read_key_safe, kbhit
from state import CHARACTER_STYLES, has_chr_file

console = Console()

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


def display_poem(poem_obj: Any, engine: Any):
    title = getattr(poem_obj, "title", "Poem")
    author = getattr(poem_obj, "author", "Unknown")
    text = getattr(poem_obj, "text", "")
    
    author_key = str(author).lower()
    style_info = CHARACTER_STYLES.get(author_key, CHARACTER_STYLES.get(author, {"color": "bold pink1", "border": "pink1"}))
    
    poem_panel = Panel(
        Text(text, style="italic white"),
        title=f"[{style_info['color']}]{title}[/]",
        subtitle=" [bold dim]Press [Space/Enter] to finish reading[/bold dim] ",
        border_style=style_info["border"],
        width=75
    )
    
    set_cbreak()
    try:
        with Live(poem_panel, auto_refresh=False) as live:
            live.refresh()
            if IS_TTY:
                while True:
                    key = read_key_safe()
                    if key in (" ", "\r", "\n"):
                        break
            else:
                try:
                    import sys
                    sys.stdin.readline()
                except Exception:
                    time.sleep(2.0)
    finally:
        restore_cbreak()
        if engine and hasattr(engine, "state"):
            persistent_pt = getattr(engine.state.get("persistent"), "playthrough", 0)
            if persistent_pt != 3:
                config_obj = engine.state.get("config")
                if config_obj:
                    config_obj.allow_skipping = True
                engine.state["allow_skipping"] = True


def handle_special_poem(args_str: str, engine: Any) -> bool:
    for p_key, p_data in SPECIAL_POEMS.items():
        if p_key in args_str:
            dummy = SpecialPoemObj(p_data["title"], p_data["author"], p_data["text"])
            display_poem(dummy, engine)
            return True
    return False


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
    
    import readchar
    
    words = []
    poemwords_path = os.path.join(os.getcwd(), "game_scripts", "poemwords.txt")
    
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
    
    persistent_obj = state.get("persistent")
    persistent_pt = getattr(persistent_obj, "playthrough", 0) if persistent_obj else 0

    sayori_active = (persistent_pt == 0) and has_chr_file("sayori.chr")
    
    panel = Panel(Text("Initializing..."), title="Poem Game", width=80)
    
    set_cbreak()
    try:
        with Live(panel, auto_refresh=False) as live:
            for round_num in range(1, 21):
                if persistent_pt >= 3:
                    glitch_options = [
                        "Just Monika", "Monika", "M0n1k4", "E R R O R", 
                        "¡¢£¤¥¦", "Delete", "Love", "Forever", 
                        "Just Monika", "Monika", "Noth1ng", "A1w4ys"
                    ]
                    round_words = [
                        {"word": w, "s": 0, "n": 0, "y": 0, "m": 3}
                        for w in random.sample(glitch_options, 10)
                    ]
                else:
                    sampled = random.sample(words, 10)
                    if persistent_pt in (1, 2):
                        # 20% chance to corrupt words in Act 2
                        corrupted = []
                        for item in sampled:
                            if random.random() < 0.2:
                                corrupted.append({"word": "¡¢£¤¥¦", "s": 0, "n": item["n"], "y": item["y"], "m": 1})
                            else:
                                corrupted.append(item)
                        round_words = corrupted
                    else:
                        round_words = sampled

                selected_idx = 0
                running = True
                
                while running:
                    table = Table(box=None, show_header=False, width=72)
                    table.add_column("words", width=32)
                    table.add_column("status", width=36)
                    
                    words_text = Text()
                    words_text.append(f"Choose a word:\n\n", style="bold yellow")
                    for idx, w in enumerate(round_words):
                        if idx == selected_idx:
                            words_text.append(f" ->  {w['word']} \n", style="reverse bold cyan")
                        else:
                            words_text.append(f"     {w['word']} \n")
                            
                    status_text = Text()
                    status_text.append(f"Progress: {round_num}/20\n\n", style="bold magenta")
                    status_text.append("Selection Log:\n", style="bold yellow")
                    for sw_word, sw_char, sw_color in recent_selections[-6:]:
                        status_text.append(f" • {sw_word} ", style="white")
                        status_text.append(f"({sw_char})\n", style=sw_color)
                        
                    table.add_row(words_text, status_text)
                    
                    panel.renderable = table
                    panel.subtitle = f" [bold dim]Select: [Space/Enter] | Navigate: [Up/Down][/bold dim] "
                    live.refresh()
                    
                    key = read_key_safe()
                    if IS_TTY and key in (readchar.key.UP, "w", "W"):
                        selected_idx = (selected_idx - 1) % 10
                    elif IS_TTY and key in (readchar.key.DOWN, "s", "S"):
                        selected_idx = (selected_idx + 1) % 10
                    elif not IS_TTY or key in (readchar.key.ENTER, readchar.key.SPACE, "\r", "\n", " "):
                        chosen = round_words[selected_idx]
                        s_pts, n_pts, y_pts = chosen["s"], chosen["n"], chosen["y"]
                        sPointTotal += s_pts
                        nPointTotal += n_pts
                        yPointTotal += y_pts
                        
                        # Determine who liked the word
                        if persistent_pt >= 3:
                            reaction = ("💚 Monika", "green")
                        elif sayori_active and s_pts >= max(n_pts, y_pts):
                            reaction = ("🩵 Sayori", "sky_blue1")
                        elif n_pts >= y_pts:
                            reaction = ("🩷 Natsuki", "pink1")
                        else:
                            reaction = ("💜 Yuri", "medium_purple3")
                            
                        recent_selections.append((chosen["word"], reaction[0], reaction[1]))
                        running = False
    finally:
        restore_cbreak()

    chapter = state.get("chapter", 0)
    playthrough = state["persistent"].playthrough
    poemwinner = state.get("poemwinner", ["sayori", "sayori", "sayori"])
    
    if playthrough >= 3:
        winner = "monika"
    elif playthrough == 0:
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
    
    if winner == "sayori":
        state["s_appeal"] = state.get("s_appeal", 0) + 1
        state["s_poemappeal"][chapter] = 1
    elif winner == "natsuki":
        state["n_appeal"] = state.get("n_appeal", 0) + 1
        state["n_poemappeal"][chapter] = 1
    elif winner == "yuri":
        state["y_appeal"] = state.get("y_appeal", 0) + 1
        state["y_poemappeal"][chapter] = 1
        
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
    console.print(f"Winner: [bold cyan]{winner.capitalize()}[/]\n")
    time.sleep(1.5)

    if playthrough != 3:
        config_obj = state.get("config")
        if config_obj:
            config_obj.allow_skipping = True
        state["allow_skipping"] = True
