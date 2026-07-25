# 🎀 Doki Doki CLI Club! (DDCC)

![](https://img.shields.io/badge/💚_Just-Monika-green)
![](https://img.shields.io/badge/Python-3.7%2B-blue)
![](https://img.shields.io/badge/CLI-Terminal_Visual_Novel-pink)

> *"Welcome to the Literature Club... now running directly inside your favorite terminal interface."* 💚

```
┌──────────────────────────────────────────────────────────┐
│              🎀 DOKI DOKI CLI CLUB! 🎀                  │
│   "Welcome to the Literature Club... in your shell."     │
└──────────────────────────────────────────────────────────┘
```

**Doki Doki CLI Club! (DDCC)** is an ultra-lightweight, high-performance command-line interpreter that plays *Doki Doki Literature Club* directly within your terminal. 

Enjoy rich dialogue, interactive menus, character-accurate color themes, full Ren'Py text tag markup, character poem readers, and an in-place TUI poem writing minigame—all powered by Python, [rich](https://pypi.org/project/rich/), and [readchar](https://pypi.org/project/readchar/).

---

## ✨ Key Features

* ⚡ **Zero-GUI Overhead**: Read the visual novel directly over SSH, in headless environments, or in your favorite terminal emulator.
* 🎨 **Character Theme Styling**:
  * 🩵 **Sayori**: Sky Blue (`sky_blue1`)
  * 🩷 **Natsuki**: Pastel Pink (`pink1`)
  * 💚 **Monika**: Emerald Green (`green`)
  * 💜 **Yuri**: Deep Purple (`purple`)
* 📜 **Dedicated TUI Poem Console Reader**: Renders character handwritten poems (`poem_s1`, `poem_n1`, `poem_y1`, `poem_m1`, special poems) inside styled Rich panels matching each girl's color scheme, complete with in-game hotkeys (`Space` to finish reading, `[G]` to save, `[L]` to load) and clean terminal history logs.
* 📖 **Ren'Py Text Tag Markup**: Parses and translates `{i}` (italics), `{b}` (bold), `{u}` (underline), `{s}` (strikethrough), and `{color=...}` tags into Rich terminal styles in real-time, with automatic tag closing during typewriter animations.
* 🎮 **Bottom Dialogue Quick-Menu**:
  * `[Space]` : Advance to the next line of dialogue / fast-forward typewriter.
  * `[A]` : Toggle **Auto-Play** mode (automatically advances after reading delays).
  * `[S]` : Toggle **Skip Mode** (instantly fast-forwards; press any key to interrupt).
  * `[G]` : **Save Game** state to disk (`savegame.json`).
  * `[L]` : **Load Game** state from disk (available in-game and at initial launch).
* 📝 **In-Place Split TUI Poem Minigame**: Refactored to render within a single `Live` panel block (zero terminal scroll clutter), featuring a 2-column layout displaying word choices on the left, and live progress, girl appeal scores, and recent word history on the right.
* 🎯 **In-Place TUI Decision Menus**: Interactive choice selection with embedded prompt headers, keyboard navigation (`Up/Down`, `W/S`), and in-place frame updates.
* 🔀 **Dynamic Ren'Py Control Flow**: Full AST parser support for `call expression` and `jump expression` statements, evaluating dynamic script variables (`poemwinner`, `nextscene`) against runtime game state.
* 💾 **Bulletproof JSON Save System**: Trial-validated state serialization that safely filters runtime classes, functions, and modules to guarantee error-free save file generation.
* ⚙️ **On-The-Fly RPA Unpacker & Decompiler**: Automatically extracts `.rpyc` script bytecode from official RPA archives and decompiles them into `.rpy` source scripts using `rpycdec`.

---

## 🚀 Setup & Execution

### 1. Prerequisites
Ensure you have Python 3.7+ installed. Install the required dependencies:
```bash
pip install rich readchar rpycdec
```

### 2. Prepare Game Files
Place the official PC game directory named **`DDLC-1.1.1-pc`** into the root of this repository. Your directory layout should look like this:
```
DDCC/
├── DDLC-1.1.1-pc/       # Place the official DDLC game directory here
├── decompile_scripts.py
├── engine.py
├── parser.py
└── README.md
```

### 3. Extract & Decompile Scripts
Run the extraction utility to unpack `.rpa` archives and decompile `.rpyc` bytecode into readable `.rpy` scripts:
```bash
python decompile_scripts.py
```
*This generates a `game_scripts/` directory containing all game `.rpy` source files.*

### 4. Run the Game!
Start the visual novel interpreter:
```bash
python engine.py
```

---

## 🕹️ Controls & Hotkeys

| Action | Shortcut Key | Description |
| :--- | :---: | :--- |
| **Next Line / Finish Poem** | `Space` | Advance dialogue / finish reading poem / fast-forward typewriter |
| **Auto-Play** | `A` | Toggle automatic line advancement |
| **Skip Mode** | `S` | Fast-forward all dialogue; press any key to stop |
| **Save Game** | `G` | Save current game state to `savegame.json` |
| **Load Game** | `L` | Load last saved game state (in-game or at startup) |
| **Menu Select** | `Enter` / `Space` | Confirm selection in Decision menu or Poem minigame |
| **Navigate** | `Up` / `Down` or `W` / `S` | Move cursor in menus |

---

## 🛠️ Architecture Overview

* **[decompile_scripts.py](file:///home/bgkang/Projects/DDCC/decompile_scripts.py)**: Extracts `scripts.rpa`, runs `rpycdec` bytecode decompilation to `.rpy`, and cleans up output folders.
* **[parser.py](file:///home/bgkang/Projects/DDCC/parser.py)**: Indentation-based Ren'Py syntax parser. Constructs structured AST nodes (`label`, `dialogue`, `if/elif/else`, `menu`, `call_expr`, `jump_expr`, `python_block`).
* **[engine.py](file:///home/bgkang/Projects/DDCC/engine.py)**: Main runtime engine. Features non-blocking TTY input handling, state sandbox evaluation, Rich panel rendering, `display_poem()` TUI console, save/load serialization, and the interactive Poem writing minigame.
