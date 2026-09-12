# backtalk: talk to your Claude Code agent out loud.
# Copyright (C) 2026 Jared Rhodenizer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session log — terminal print + timestamped append to logs/backtalk.log.

Exists because the hardest voice bug ever hit here (the off-by-one
interrupt desync) had to be diagnosed from source, because the session
only printed to a terminal window nobody saved. Every load-bearing line
([you], replies, interrupts, drain/rebuild events, TTS fallbacks) goes
through log() so the next gremlin comes with receipts.
"""
import datetime
import os
import re
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "backtalk.log"

# ---- Console color. Screen only; the log file never sees an escape code
# (see log() — the receipts this module exists to produce must stay
# greppable). Style is inferred from the "[tag]" prefix so not one of the
# ~80 existing log() call sites has to change.
_RESET = "\033[0m"
_C = {
    "you":    "\033[38;5;51m",    # bright cyan — the person
    "reply":  "\033[38;5;231m",   # near-white — the agent's spoken words
    "dim":    "\033[38;5;244m",   # grey — plumbing: ears, mouth, ptt, brain
    "tool":   "\033[38;5;180m",   # tan — a tool call mid-turn
    "think":  "\033[38;5;140m",   # muted violet — thinking / working
    "turn":   "\033[38;5;108m",   # sage — the end-of-turn stat line
    "perm":   "\033[38;5;214m",   # amber — a permission ask, must stand out
    "error":  "\033[38;5;203m",   # red — anything that failed
}
# lowercase tags that are backtalk's own plumbing; anything else in the
# "[x]" slot (i.e. the agent's name) is a spoken reply.
_SYS_DIM = {"backtalk", "ears", "mouth", "ptt", "brain", "console", "sig"}
_TAG_RE = re.compile(r"^\[([^\]]{1,20})\]")
_ERR_RE = re.compile(r"error|failed|desync|can't|couldn't|BRAIN CONNECT"
                     r"|no working|timed out", re.I)


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("BACKTALK_NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


_COLOR = False   # set by _init_console()


def _style_for(line: str) -> str | None:
    m = _TAG_RE.match(line)
    if not m:
        return None
    tag = m.group(1).strip().lower()
    if tag == "you":
        return _C["you"]         # the person's words are never "an error"
    if tag == "perm":
        return _C["perm"]
    if tag == "tool":
        return _C["tool"]
    if tag in ("think", "thinking"):
        return _C["think"]
    if tag == "turn":
        return _C["turn"]
    if tag in _SYS_DIM:
        # a plumbing line that reports a failure gets the red, not grey
        return _C["error"] if _ERR_RE.search(line) else _C["dim"]
    return _C["reply"]      # the agent's name -> a spoken line


def _init_console():
    """Ask a Windows console for UTF-8 before anything is printed at it.

    Windows consoles default to a legacy codepage (cp1252 on a UK/US
    install), so a UTF-8 em-dash arrives as mojibake: the startup banner
    rendered as "[backtalk] up a<TM>" instead of "up --". Fixing the
    banner's own characters would not have been a fix, because the
    agent's REPLIES are printed here too and can contain anything at all.

    errors="replace" on the streams means a character the terminal
    genuinely cannot draw degrades to "?" rather than raising mid
    sentence and taking the voice down. No-ops everywhere but Windows.
    """
    global _COLOR
    if sys.platform == "win32":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetConsoleOutputCP(65001)
            k32.SetConsoleCP(65001)
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x4) on stdout, so the
            # ANSI color below actually renders in a classic console.
            # Harmless if it fails; Windows Terminal / VS Code already
            # honor the codes.
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _COLOR = _color_enabled()


_init_console()


def log(line: str):
    screen = line
    if _COLOR:
        style = _style_for(line)
        if style:
            screen = f"{style}{line}{_RESET}"
    try:
        print(screen, flush=True)
    except UnicodeEncodeError:
        # Last resort if the console refused UTF-8: readable beats fatal.
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # encoding pinned on purpose. The default is the platform's, which
        # on Windows is that same legacy codepage -- so the log file kept
        # its own permanently corrupted copy of every line the console had
        # already mangled, and the receipts this module exists to produce
        # were unreadable exactly where they were most needed.
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")
    except Exception:
        pass  # a broken log file must never take the voice down
