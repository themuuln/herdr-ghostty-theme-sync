# Ghostty Theme Sync for herdr

Adapt herdr's theme and sidebar colors to the active [Ghostty](https://ghostty.org)
theme, and keep sidebar tokens alive across herdr restarts.

## Why

- **Theme drift**: herdr's palette is hardcoded in `config.toml`; Ghostty's is
  in its theme file. Change one and the other goes stale. This tool derives
  herdr's colors from Ghostty's theme, so the sidebar, panels, and borders
  always match the terminal.
- **Sidebar token rot**: herdr sidebar tokens (workspace name/dir/pane counts,
  per-project colors) are ephemeral server state — a herdr restart wipes them,
  leaving the spaces/agents panels blank until someone re-pushes. `refresh.sh`
  re-pushes everything from the live snapshot.
- **Built-in tokens ignore color**: herdr's built-in `workspace`/`agent` tokens
  render in *state colors* (orange while working, green while idle) and ignore
  `fg`. Custom `$tokens` honor `fg` exactly — this tool uses `$name` and
  per-project `$tokens` so names stay consistently colored.
- **State icons conflate done and idle**: herdr 0.8.0's `state_icon` (Dots
  style) renders `done` and `working` as solid dots and `idle` as an outline.
  The companion omp extension pushes per-state `$st_*` tokens with distinct,
  colored symbols (`●` yellow working / `✓` green done / `○` dim idle / `×`
  red blocked) so finished agents are instantly visible.

## Install

As a herdr plugin (from [herdr.dev/plugins](https://herdr.dev/plugins)):

```bash
herdr plugin install themuuln/herdr-ghostty-theme-sync --yes
herdr plugin action list          # ghostty-theme-sync.sync / ghostty-theme-sync.refresh
```

Or standalone:

```bash
git clone https://github.com/themuuln/herdr-ghostty-theme-sync
cd herdr-ghostty-theme-sync
./install.sh                 # scripts → ~/.local/bin
./install.sh --with-auto-sync    # + launchd watcher (macOS)
```

## Usage

Copy the theme/sidebar rows from `config.example.toml` into
`~/.config/herdr/config.toml`, then:

```bash
herdr-theme-sync        # derive colors from the active Ghostty theme + reload + refresh
herdr-refresh-sidebar   # re-push sidebar tokens (after a herdr restart)
```

Keybinding (recommended):

```toml
[[keys.command]]
key = "prefix+alt+s"
type = "shell"
command = "herdr-theme-sync"
description = "sync herdr theme from ghostty"
```

### Auto-sync (optional, macOS)

`install.sh --with-auto-sync` installs a launchd `WatchPaths` agent that runs
`herdr-auto-sync` whenever:

- `~/.config/ghostty/config` or `~/.config/ghostty/themes` changes (ghostty
  theme switch → herdr follows automatically), or
- the herdr server socket is recreated (herdr restart → tokens re-pushed).

The agent retries while herdr boots and is fully idempotent.

## Per-project colors

`refresh.sh` reads an optional `~/.config/herdr/refresh-projects.conf`:

```bash
# keys the sidebar config styles; $misc catches unmapped directories
PROJECT_KEYS="zuiio tolom zer onoo herdr omp archive horoscope misc"
# basename=token pairs
PROJECT_BY_BASENAME="zuiio=zuiio tolom=tolom zer=zer onoo=onoo herdr=herdr omp=omp"
# path-prefix=token pairs
PROJECT_BY_PATH="~/.omp=omp ~/archive=archive ~/horoscope-bot=horoscope"
# optional: path to the omp metadata extension → also re-push its pane tokens
OMP_EXT="/path/to/herdr-omp-agent-metadata.ts"
```

Each token gets its own `fg` in the sidebar rows (see `config.example.toml`);
`refresh.sh` reports only the active project per pane, clearing the others.

## How it works

1. `theme-sync.py` reads `theme = ...` from `~/.config/ghostty/config`,
   resolves the theme file (user themes dir, then the Ghostty bundle),
   and maps its palette onto herdr:
   - `[theme.custom]` tokens (text/subtext0/surface*/accent/mauve/green/...)
   - every sidebar token `fg` by semantic role (name, branch, git_status,
     dir, panes, per-project colors, per-agent accents)
   - bright palette variants (8–15) for anything that must pop on dark themes
   - validates with `herdr config check` (auto-restores the backup on failure)
     and live-reloads via `herdr server reload-config`
2. `refresh.sh` reads `herdr api snapshot` once and re-pushes workspace tokens
   (`name`/`dir`/`path`/`panes`) and pane tokens (`dir`/`path`, plus omp
   extension tokens when configured) — one pass, no per-pane process spawns.

## Files

| File | Purpose |
|---|---|
| `theme-sync.py` | Ghostty palette → herdr config rewrite |
| `refresh.sh` | Sidebar token re-push from the live snapshot |
| `herdr-auto-sync` | launchd wrapper (retries while herdr boots) |
| `install.sh` | Script + launchd agent installer |
| `config.example.toml` | Adaptive theme/sidebar rows for herdr |
| `herdr-plugin.toml` | herdr.dev plugin manifest |

## License

MIT
