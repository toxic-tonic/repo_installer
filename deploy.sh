#!/usr/bin/env bash
# Baut das Release-ZIP fuer custom_components/repo_installer.
#
#   ./deploy.sh zip   baut dist/repo_installer-<version>-<kurzhash>.zip und
#                     dist/repo_installer.zip (inhaltsgleich, fuer HACS)
#
# Gebaut wird deterministisch mit scripts/build_zip.py, derselben Logik wie im
# GitHub-Release-Workflow: gleicher Commit -> gleiche SHA-256.
#
# Nur von einem sauberen, gepushten master-Stand.
set -euo pipefail

MODE="${1:-}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

git -C "$REPO_DIR" fetch -q origin
[[ "$(git -C "$REPO_DIR" branch --show-current)" == master ]] || { echo "nicht auf master" >&2; exit 1; }
[[ -z "$(git -C "$REPO_DIR" status --porcelain)" ]] || { echo "Arbeitskopie nicht sauber" >&2; exit 1; }
[[ "$(git -C "$REPO_DIR" rev-parse HEAD)" == "$(git -C "$REPO_DIR" rev-parse origin/master)" ]] \
  || { echo "master entspricht nicht origin/master" >&2; exit 1; }

case "$MODE" in
  zip)
    # dist/ enthaelt nur die ZIPs des aktuellen Releases
    mkdir -p "$REPO_DIR/dist"
    rm -f "$REPO_DIR"/dist/repo_installer*.zip
    python3 "$REPO_DIR/scripts/build_zip.py" --repo "$REPO_DIR" --ref HEAD --out "$REPO_DIR/dist"
    ;;
  *)
    echo "Aufruf: $0 zip" >&2
    exit 1
    ;;
esac
