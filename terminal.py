import sys
import time
import signal
import readchar
from rich.console import Console

console = Console()

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

_last_ctrl_c_time = 0.0

def handle_ctrl_c():
    global _last_ctrl_c_time
    now = time.time()
    if now - _last_ctrl_c_time < 2.0:
        restore_cbreak()
        console.print("\n[bold pink1]Goodbye! Thanks for visiting the Literature Club! 🎀[/]\n")
        sys.exit(0)
    else:
        _last_ctrl_c_time = now
        console.print("\n[bold yellow]Press Ctrl+C again within 2 seconds to quit![/]")

def sigint_handler(sig, frame):
    handle_ctrl_c()

try:
    signal.signal(signal.SIGINT, sigint_handler)
except Exception:
    pass

def read_key_safe() -> str:
    if not IS_TTY:
        try:
            line = sys.stdin.readline()
            return line if line else "\n"
        except Exception:
            time.sleep(1.0)
            return "\n"
    try:
        key = readchar.readkey()
        if key == readchar.key.CTRL_C or key == "\x03":
            handle_ctrl_c()
            return ""
        return key
    except KeyboardInterrupt:
        handle_ctrl_c()
        return ""
