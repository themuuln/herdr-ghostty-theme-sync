#!/usr/bin/env bash
# herdr-refresh-sidebar — re-push herdr sidebar tokens from the live snapshot.
#
# Why: sidebar tokens are ephemeral server state — they do not survive a herdr
# restart, and extensions/CLI pushes only happen at session start. This script
# re-reads the live herdr snapshot and re-pushes:
#   - workspace tokens: name/dir/path/panes (spaces panel)
#   - pane tokens: dir/path for every agent pane
#   - omp extension tokens (optional): stateline/summary/project key for omp
#     agent panes, when the omp metadata extension is present
#
# Run manually when the sidebar looks stale, after a herdr restart, or from a
# keybinding / launchd watcher.

set -euo pipefail

# --- Optional per-user config ----------------------------------------------
# Drop a file at ~/.config/herdr/refresh-projects.conf to customize:
#   PROJECT_KEYS="zuiio tolom ..."          keys the sidebar config styles
#   PROJECT_BY_BASENAME="zuiio=zuiio ..."   basename=token pairs
#   PROJECT_BY_PATH="~/.omp=omp ..."        path-prefix=token pairs
#   OMP_EXT="/path/to/herdr-omp-agent-metadata.ts"   (enable omp pane tokens)
# ---------------------------------------------------------------------------
PROJECT_KEYS=""
PROJECT_BY_BASENAME=""
PROJECT_BY_PATH=""
OMP_EXT=""
if [ -f "$HOME/.config/herdr/refresh-projects.conf" ]; then
  # shellcheck source=/dev/null
  . "$HOME/.config/herdr/refresh-projects.conf"
fi

SOURCE="${SOURCE:-omp:metadata}"

# project_token_key REL_PATH -> token
# Mirrors the omp extension's projectTokenKey: basename map, then path-prefix
# map, then a sanitized basename (only when the sidebar config styles it),
# otherwise the "misc" fallback.
project_token_key() {
  local rel="$1" base key pair
  base="${rel##*/}"
  for pair in $PROJECT_BY_BASENAME; do
    [ "${pair%%=*}" = "$base" ] && { echo "${pair#*=}"; return; }
  done
  for pair in $PROJECT_BY_PATH; do
    case "$rel" in
      "${pair%%=*}" | "${pair%%=*}/"*) echo "${pair#*=}"; return ;;
    esac
  done
  key="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/_/g; s/^_+|_+$//g')"
  if [ -n "$PROJECT_KEYS" ] && [[ " $PROJECT_KEYS " == *" $key "* ]]; then
    echo "$key"
  else
    echo "misc"
  fi
}

clears_except() {
  local keep="$1" out="" k
  for k in $PROJECT_KEYS; do
    [ "$k" != "$keep" ] && out="$out --clear-token $k"
  done
  echo "$out"
}

SNAPSHOT="$(herdr api snapshot 2>/dev/null || true)"
[ -z "$SNAPSHOT" ] && { echo "herdr: no snapshot (server down?)" >&2; exit 1; }

# --- pane tokens -------------------------------------------------------------
# One pass: dir/path for every agent pane; omp extras (stateline/summary/
# project key) when the omp extension is configured.
OMP_ACTIVE=0
[ -n "$OMP_EXT" ] && [ -f "$OMP_EXT" ] && OMP_ACTIVE=1
echo "Refreshing pane tokens…"
# shellcheck disable=SC2086
echo "$SNAPSHOT" | jq -r '.result.snapshot.agents[] | [.pane_id, .agent, (.agent_status // "?"), ((.terminal_title // "") | sub("^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏>!✓?] ?"; "")), (.cwd // "")] | @tsv' |
while IFS=$'\t' read -r pid agent status label cwd; do
  g="?"
  st="·"
  case "$status" in
    working) g="⠋"; st="◐" ;;
    idle) g=">"; st="○" ;;
    done) g="✓"; st="✓" ;;
    blocked) g="!"; st="×" ;;
  esac
  if [ -n "$cwd" ] && [ "$cwd" != "$HOME" ]; then
    case "$cwd" in "$HOME"*) rel="~${cwd#$HOME}";; *) rel="$cwd";; esac
    dir="$(basename "$rel")"
    [ -z "$dir" ] && dir="~"
    if [ "$OMP_ACTIVE" = "1" ] && [ "$agent" = "omp" ]; then
      key="$(project_token_key "$rel")"
      herdr pane report-metadata "$pid" --source "$SOURCE" --agent omp --display-agent "π" \
        --token "stateline=$g $label" --token "summary=$label" --token "dir=$dir" --token "path=$rel" \
        --token "state=$st" --token "$key=$dir" $(clears_except "$key") >/dev/null 2>&1
      echo "  pane $pid → $key ($dir) [$st]"
    else
      herdr pane report-metadata "$pid" --source "$SOURCE" \
        --token "dir=$dir" --token "path=$rel" --token "state=$st" >/dev/null 2>&1
      echo "  pane $pid → dir=$dir [$st]"
    fi
  elif [ "$OMP_ACTIVE" = "1" ] && [ "$agent" = "omp" ]; then
    # cwd unknown or still at HOME during agent boot — keep existing project
    # tokens (the extension owns them once the session is ready).
    herdr pane report-metadata "$pid" --source "$SOURCE" --agent omp --display-agent "π" \
      --token "stateline=$g $label" --token "summary=$label" --token "state=$st" >/dev/null 2>&1
    echo "  pane $pid → (cwd booting, project tokens untouched) [$st]"
  fi
done

# --- workspace tokens --------------------------------------------------------
# Spaces panel: $name is the workspace label (fixed-color custom token), plus
# dir/path/panes on the context line.
echo "Refreshing workspace tokens…"
# shellcheck disable=SC2086
echo "$SNAPSHOT" | jq -r '.result.snapshot.workspaces[] | [.workspace_id, .label, (.pane_count // 0), (.tab_count // 0)] | @tsv' |
while IFS=$'\t' read -r wid label pane_count tab_count; do
  cwd="$(echo "$SNAPSHOT" | jq -r --arg wid "$wid" '.result.snapshot.panes[] | select(.workspace_id == $wid) | .cwd // empty' | head -1)"
  case "$cwd" in "$HOME"*) rel="~${cwd#$HOME}";; *) rel="$cwd";; esac
  dir="$(basename "$rel")"
  [ -z "$dir" ] && dir="~"
  herdr workspace report-metadata "$wid" --source "$SOURCE" \
    --token "name=$label" --token "dir=$dir" --token "path=$rel" \
    --token "panes=$pane_count pane$( [ "$pane_count" = "1" ] && echo "" || echo "s" )" \
    $(clears_except "") >/dev/null 2>&1
  echo "  workspace $wid → name=$label dir=$dir · $pane_count panes"
done

echo "Done."
