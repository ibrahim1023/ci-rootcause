#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_live_github_test.sh \
    --repo-path /path/to/disposable/repo \
    --repository owner/repo \
    --token <github_token> \
    [--target-branch main] \
    [--pytest-args "<extra pytest args>"]

Description:
  Runs the opt-in live GitHub integration test:
    tests/integration/test_pr_creation_live_github.py

  The script exports required env vars for the test and prints cleanup guidance.
EOF
}

REPO_PATH=""
REPOSITORY=""
TOKEN=""
TARGET_BRANCH="main"
PYTEST_ARGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-path)
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --repository)
      REPOSITORY="${2:-}"
      shift 2
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2
      ;;
    --target-branch)
      TARGET_BRANCH="${2:-}"
      shift 2
      ;;
    --pytest-args)
      PYTEST_ARGS="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$REPO_PATH" || -z "$REPOSITORY" || -z "$TOKEN" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 2
fi

if [[ "$REPOSITORY" != */* ]]; then
  echo "--repository must be in owner/repo format." >&2
  exit 2
fi

if [[ ! -d "$REPO_PATH" ]]; then
  echo "--repo-path does not exist: $REPO_PATH" >&2
  exit 2
fi

if [[ ! -d "$REPO_PATH/.git" ]]; then
  echo "--repo-path is not a git repository: $REPO_PATH" >&2
  exit 2
fi

export CI_ROOTCAUSE_LIVE_GITHUB=1
export CI_ROOTCAUSE_LIVE_REPO_PATH="$REPO_PATH"
export CI_ROOTCAUSE_LIVE_REPOSITORY="$REPOSITORY"
export CI_ROOTCAUSE_LIVE_GITHUB_TOKEN="$TOKEN"
export CI_ROOTCAUSE_LIVE_TARGET_BRANCH="$TARGET_BRANCH"

echo "Running live GitHub integration test..."
echo "  repo_path: $CI_ROOTCAUSE_LIVE_REPO_PATH"
echo "  repository: $CI_ROOTCAUSE_LIVE_REPOSITORY"
echo "  target_branch: $CI_ROOTCAUSE_LIVE_TARGET_BRANCH"

if [[ -n "$PYTEST_ARGS" ]]; then
  # shellcheck disable=SC2086
  pytest tests/integration/test_pr_creation_live_github.py -q $PYTEST_ARGS
else
  pytest tests/integration/test_pr_creation_live_github.py -q
fi

echo
echo "Live test finished."
echo "Cleanup checklist:"
echo "1. Close the created PR in https://github.com/$REPOSITORY/pulls"
echo "2. List generated fix branches:"
echo "   git -C \"$REPO_PATH\" ls-remote --heads origin 'ci-rootcause/fix/*'"
echo "3. Delete an individual branch:"
echo "   git -C \"$REPO_PATH\" push origin --delete <branch_name>"
echo "4. Revoke/delete the temporary GitHub token if it was single-use."
