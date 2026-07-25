# 🎀 Doki Doki CLI Club! (DDCC)

![](https://img.shields.io/badge/💚_Just-Monika-green)

> "Welcome to the Literature Club... now running directly inside your favorite terminal interface." 💚

```
┌──────────────────────────────────────────────────────────┐
│              🎀 DOKI DOKI CLI CLUB! 🎀                  │
│   "Welcome to the Literature Club... in your shell."     │
└──────────────────────────────────────────────────────────┘
```

**Doki Doki CLI Club! (DDCC)** is an ultra-lightweight, high-performance command-line interpreter that plays *Doki Doki Literature Club* directly within your terminal. 

Enjoy rich dialogue, interactive menus, color-coded character themes, and an interactive CLI poem writing minigame—all powered by Python, [rich](https://pypi.org/project/rich/), and [readchar](https://pypi.org/project/readchar/).

---

## ✨ Features
* ⚡ **Zero-GUI Overhead**: Read the visual novel directly over SSH, in low-spec environments, or just in your favorite shell.
* 🎨 **Rich Typewriter Dialogues**: Colored border panels matching character themes (pink for Sayori, magenta for Natsuki, purple for Yuri, green for Monika) with typewriter typing animation and keypress skip/fast-forward support.
* 📝 **Interactive CLI Poem Game**: Complete arrow-key controlled CLI minigame that maps points and calculates character appeal values using the original game formulas.
* 🐚 **Hacker Aesthetic & Muted Stage Directions**: Character movements (`show`, `hide`, `scene`) and background audio changes (`play/stop music`) are logged as elegant, non-intrusive console indicators.
* ⚙️ **On-the-Fly script extraction**: Unpacks original `.rpa` files and decompiles `.rpyc` scripts on-the-fly from the official game files using `rpycdec`.

---

## 🚀 Setup & Execution

### 1. Prerequisites
Ensure you have Python 3.7+ installed. Install the required console packages:
```bash
pip install rich readchar rpycdec
```

### 2. Prepare Game Files
Place the official PC game directory named **`DDLC-1.1.1-pc`** into the root of this project folder. Your workspace should look like this:
```
DDCC/
├── DDLC-1.1.1-pc/       # Place the official DDLC game directory here
├── decompile_scripts.py
├── engine.py
├── parser.py
└── README.md
```

### 3. Extract & Decompile Scripts
Run the extraction utility to extract raw assets and decompile `.rpyc` bytecode into readable `.rpy` scripts:
```bash
python decompile_scripts.py
```
This will generate a `game_scripts/` folder containing all game `.rpy` source files.

### 4. Run the Game!
Start the visual novel interpreter:
```bash
python engine.py
```

---

## 🛠️ Project Structure
* [decompile_scripts.py](file:///home/bgkang/Projects/DDCC/decompile_scripts.py): Automatically reads the `game/scripts.rpa` archive, extracts script bytecode, runs `rpycdec` to decompile them into `.rpy`, and cleans up.
* [parser.py](file:///home/bgkang/Projects/DDCC/parser.py): An indentation-based Ren'Py syntax parser that generates a structured AST tree representing game blocks, dialogue, conditional flow, and menus.
* [engine.py](file:///home/bgkang/Projects/DDCC/engine.py): The main runtime engine. Manages execution stacks, evaluates python expressions, handles input selections, runs the console poem game, and types out dialogue boxes.
