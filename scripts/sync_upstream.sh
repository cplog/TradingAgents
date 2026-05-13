#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/sync_upstream.sh [options]

Sync local main with upstream/main, then push main to origin.

Options:
  --branch <name>   Also rebase this branch onto updated main.
  --rebase-current  Rebase the currently checked-out branch onto updated main.
  --autostash       Temporarily stash local changes before syncing.
  -h, --help        Show this help.
EOF
}

branch_to_rebase=""
rebase_current=0
autostash=0

while (($#)); do
  case "$1" in
    --branch)
      if (($# < 2)); then
        echo "Error: --branch requires a branch name." >&2
        exit 1
      fi
      branch_to_rebase="$2"
      shift 2
      ;;
    --rebase-current)
      rebase_current=1
      shift
      ;;
    --autostash)
      autostash=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument '$1'." >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$branch_to_rebase" && $rebase_current -eq 1 ]]; then
  echo "Error: use either --branch or --rebase-current, not both." >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: run this script from inside a git repository." >&2
  exit 1
fi

if ! git remote get-url upstream >/dev/null 2>&1; then
  echo "Error: remote 'upstream' is missing." >&2
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "Error: remote 'origin' is missing." >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
if [[ -z "$current_branch" ]]; then
  echo "Error: detached HEAD is not supported." >&2
  exit 1
fi

stashed=0
stash_ref=""
completed=0
stash_name="sync-upstream-$(date +%Y%m%d-%H%M%S)"
if [[ $autostash -eq 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    git stash push -u -m "$stash_name" >/dev/null
    stashed=1
    stash_ref="$(git stash list -1 --format="%gd")"
  fi
elif [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree is not clean. Commit/stash changes first or use --autostash." >&2
  exit 1
fi

restore_stash() {
  if [[ $stashed -eq 1 ]]; then
    if [[ $completed -ne 1 ]]; then
      echo "Sync did not finish cleanly; kept stashed changes as ${stash_ref:-$stash_name}." >&2
      return
    fi

    set +e
    if [[ -n "$stash_ref" ]]; then
      git stash pop "$stash_ref" >/dev/null
    else
      git stash pop >/dev/null
    fi
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      echo "Warning: stash pop had conflicts. Resolve manually." >&2
    fi
  fi
}

trap restore_stash EXIT

echo "Fetching remotes..."
git fetch --prune upstream
git fetch --prune origin

echo "Updating local main from upstream/main..."
git switch main >/dev/null
git rebase upstream/main

echo "Pushing main to origin..."
git push origin main

target_branch=""
if [[ -n "$branch_to_rebase" ]]; then
  target_branch="$branch_to_rebase"
elif [[ $rebase_current -eq 1 ]]; then
  target_branch="$current_branch"
fi

if [[ -n "$target_branch" && "$target_branch" != "main" ]]; then
  echo "Rebasing ${target_branch} onto main..."
  git switch "$target_branch" >/dev/null
  git rebase main
fi

if [[ -z "$target_branch" ]]; then
  git switch "$current_branch" >/dev/null
fi

completed=1
echo "Done. main matches upstream/main and origin/main is updated."
