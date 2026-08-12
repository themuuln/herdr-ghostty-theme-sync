#!/usr/bin/env python3
"""herdr-theme-sync — derive herdr's theme + sidebar colors from the active Ghostty theme.

Reads the active `theme = ...` from ~/.config/ghostty/config, resolves the theme
file (user themes dirs first, then the Ghostty bundle), maps its palette onto
herdr's [theme.custom] tokens and every sidebar token fg in
~/.config/herdr/config.toml, then validates and reloads herdr.

Usage:
  herdr-theme-sync            apply (rewrites config, reloads herdr)
  herdr-theme-sync --dry-run  print what would change without writing
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
GHOSTTY_CONFIG = HOME / ".config" / "ghostty" / "config"
HERDR_CONFIG = HOME / ".config" / "herdr" / "config.toml"
DRY = "--dry-run" in sys.argv


def fail(msg: str) -> None:
    print(f"herdr-theme-sync: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Ghostty theme resolution
# ---------------------------------------------------------------------------

def active_theme_name() -> str:
    if not GHOSTTY_CONFIG.exists():
        fail(f"no ghostty config at {GHOSTTY_CONFIG}")
    for line in GHOSTTY_CONFIG.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == "theme":
            return v.strip().strip("\"'")
    fail("no active `theme = ...` line in ghostty config")


def find_ghostty_bin() -> str:
    which = subprocess.run(["which", "ghostty"], capture_output=True, text=True).stdout.strip()
    if which:
        return which
    # Fallbacks for minimal environments (launchd, cron): brew installs,
    # .app bundles on macOS, standard Linux paths.
    for cand in (
        "/opt/homebrew/bin/ghostty",
        "/usr/local/bin/ghostty",
        "/usr/bin/ghostty",
        "/Applications/Ghostty.app/Contents/MacOS/ghostty",
        "/Applications/Ghostty-Nightly.app/Contents/MacOS/ghostty",
    ):
        if Path(cand).exists():
            return cand
    for p in sorted(Path("/Applications").glob("Ghostty*.app/Contents/MacOS/ghostty")):
        return str(p)
    return ""


def theme_file(name: str) -> Path:
    cands = [
        HOME / ".config" / "ghostty" / "themes" / name,
        HOME / ".config" / "ghostty" / "themes" / f"{name}.conf",
        HOME / ".local" / "share" / "ghostty" / "themes" / name,
        HOME / ".local" / "share" / "ghostty" / "themes" / f"{name}.conf",
    ]
    for c in cands:
        if c.exists():
            return c
    bin_path = find_ghostty_bin()
    if bin_path:
        p = Path(bin_path)
        if ".app/Contents/MacOS" in str(p):
            # /Applications/X.app/Contents/MacOS/ghostty -> Contents/Resources/ghostty/themes
            res = p.parents[1] / "Resources" / "ghostty" / "themes" / name
            if res.exists():
                return res
    fail(f"could not find theme file for '{name}' (tried user themes dirs and the Ghostty bundle)")


def parse_theme(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if k == "palette":
            for part in v.split(","):
                idx, _, col = part.strip().partition("=")
                if col:
                    out[int(idx)] = col.strip()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Palette math
# ---------------------------------------------------------------------------

def hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb2hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend: t=0 -> a, t=1 -> b."""
    return rgb2hex(round(x * (1 - t) + y * t) for x, y in zip(hex2rgb(a), hex2rgb(b)))


# ---------------------------------------------------------------------------
# Ghostty palette -> herdr colors
# ---------------------------------------------------------------------------

def compute(theme: dict) -> tuple[dict, dict, dict]:
    bg = theme.get("background") or "#000000"
    fg = theme.get("foreground") or "#ffffff"
    p = [theme.get(i) for i in range(16)]

    def px(i: int, fallback: str) -> str:
        return p[i] if p[i] else fallback

    # Muted/quiet text: the theme's own selection-foreground when present.
    dim = theme.get("selection-foreground") or mix(fg, bg, 0.45)
    # Bright palette variants (8-15) for anything that must pop on dark bg.
    green, yellow, red = px(10, fg), px(11, fg), px(9, fg)
    blue, magenta, cyan, orange = px(12, fg), px(13, fg), px(14, fg), px(9, fg)

    custom = {
        "panel_bg": "reset",  # keep ghostty glass transparency
        "accent": blue,
        "text": fg,
        "subtext0": dim,
        "surface0": mix(bg, fg, 0.05),
        "surface1": mix(bg, fg, 0.09),
        "surface_dim": mix(bg, fg, 0.03),
        "overlay0": mix(bg, fg, 0.35),
        "overlay1": mix(bg, fg, 0.55),
        "mauve": magenta,
        "green": green,
        "yellow": yellow,
        "red": red,
        "blue": blue,
        "teal": cyan,
        "peach": orange,
    }
    sidebar = {
        # names / main text
        "$name": fg, "workspace": fg, "agent": fg,
        # state glyphs — per-state colors so working/done/idle/blocked stay obvious
        "$st_working": yellow, "$st_done": green, "$st_idle": dim, "$st_blocked": red,
        "terminal_title": dim, "terminal_title_stripped": dim,
        # git + context line
        "branch": green, "git_status": yellow, "$dir": cyan, "$panes": dim,
        # project tokens (role -> palette)
        "$zuiio": blue, "$tolom": green, "$zer": magenta, "$onoo": yellow,
        "$herdr": orange, "$omp": cyan, "$archive": dim, "$horoscope": magenta,
        "$misc": cyan,
    }
    agent_accent = {"claude": orange, "codex": green, "droid": yellow}
    return custom, sidebar, agent_accent


# ---------------------------------------------------------------------------
# Config rewrite
# ---------------------------------------------------------------------------

STYLED = re.compile(r'\{ token = "([^"]+)", fg = "#[0-9a-fA-F]{3,8}"([^}]*)\}')
THEME_KEYS = ("accent", "text", "subtext0", "surface0", "surface1", "surface_dim",
              "overlay0", "overlay1", "mauve", "green", "yellow", "red", "blue",
              "teal", "peach")


def rewrite_sidebar_line(line: str, section: str, sidebar: dict, agent_accent: dict,
                         text: str, agent_key: str | None = None) -> str:
    def repl(mm: re.Match) -> str:
        tok = mm.group(1)
        if tok == "agent":
            # rows_by_agent uses `agent = [...]` key assignments inside one table
            color = agent_accent.get(agent_key or "") \
                or agent_accent.get(section.rsplit(".", 1)[-1], text)
        else:
            color = sidebar.get(tok)
            if color is None:
                return mm.group(0)
        return f'{{ token = "{tok}", fg = "{color}"{mm.group(2)}}}'

    return STYLED.sub(repl, line)


def apply(custom: dict, sidebar: dict, agent_accent: dict, name: str) -> str:
    lines = HERDR_CONFIG.read_text().splitlines()
    out, section, i = [], "", 0
    agent_key = None
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1)
            agent_key = None
            if section == "theme.custom":
                out.append(line)
                out.append('panel_bg = "reset"')
                out.append(f'# Generated by herdr-theme-sync from ghostty theme "{name}".')
                out.append("# Edit the ghostty theme, then re-run herdr-theme-sync.")
                out.append("# Sidebar stays transparent (panel_bg reset); ghostty glass blur can mute colors.")
                for k in THEME_KEYS:
                    out.append(f'{k} = "{custom[k]}"')
                i += 1
                while i < len(lines) and not re.match(r"^\[", lines[i]):
                    i += 1
                continue
        elif section.startswith("ui"):
            if section == "ui.sidebar.agents.rows_by_agent":
                km = re.match(r"^(\w+)\s*=\s*\[", line)
                if km:
                    agent_key = km.group(1)
            if section == "ui" and re.match(r'^accent\s*=\s*"', line):
                line = f'accent = "{custom["accent"]}"'
            elif 'fg = "#' in line:
                line = rewrite_sidebar_line(line, section, sidebar, agent_accent,
                                            custom["text"], agent_key)
            elif "tokyo-night palette" in line and line.lstrip().startswith("#"):
                line = "# Colors generated by herdr-theme-sync from the active ghostty theme."
                # drop continuation lines of the old palette comment (e.g. "# #9ece6a green…")
                while i + 1 < len(lines) and re.match(r"^#\s*#[0-9a-fA-F]{6}", lines[i + 1]):
                    i += 1
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------

def main() -> None:
    name = active_theme_name()
    tf = theme_file(name)
    theme = parse_theme(tf)
    custom, sidebar, agent_accent = compute(theme)

    if DRY:
        print(f"ghostty theme: {name}  ({tf})")
        print(f"bg {theme.get('background')}  fg {theme.get('foreground')}")
        print("\ntheme.custom:")
        for k in THEME_KEYS:
            print(f'  {k} = "{custom[k]}"')
        print("\nsidebar tokens:")
        for k, v in sidebar.items():
            print(f"  {k:22s} {v}")
        return

    new = apply(custom, sidebar, agent_accent, name)
    if new == HERDR_CONFIG.read_text():
        print(f"herdr config already matches ghostty theme '{name}' — nothing to do.")
    else:
        bak = Path(os.environ.get("TMPDIR", "/tmp")) / "herdr-config.toml.bak"
        bak.write_text(HERDR_CONFIG.read_text())
        HERDR_CONFIG.write_text(new)
        print(f"rewrote {HERDR_CONFIG} for ghostty theme '{name}' (backup: {bak})")

        chk = subprocess.run(["herdr", "config", "check"], capture_output=True, text=True)
        print((chk.stdout or chk.stderr).strip())
        if chk.returncode != 0:
            HERDR_CONFIG.write_text(bak.read_text())
            fail("config check failed — restored previous config")

        r = subprocess.run(["herdr", "server", "reload-config"], capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())

    # Sidebar tokens ($name/$dir/$panes, project keys) live in ephemeral
    # workspace/pane metadata — always re-push (herdr restarts wipe them even
    # when the config is unchanged).
    subprocess.run(["herdr-refresh-sidebar"], check=False)


if __name__ == "__main__":
    main()
