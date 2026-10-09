#!/usr/bin/env bash
# Baut das Release-ZIP fuer custom_components/forgejo_updater.
#
#   ./deploy.sh zip   baut dist/forgejo_updater-<version>-<kurzhash>.zip
#
# Nur von einem sauberen, gepushten master-Stand.
set -euo pipefail

MODE="${1:-}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DOMAIN=forgejo_updater
SRC="$REPO_DIR/custom_components/$DOMAIN"

git -C "$REPO_DIR" fetch -q origin
[[ "$(git -C "$REPO_DIR" branch --show-current)" == master ]] || { echo "nicht auf master" >&2; exit 1; }
[[ -z "$(git -C "$REPO_DIR" status --porcelain)" ]] || { echo "Arbeitskopie nicht sauber" >&2; exit 1; }
[[ "$(git -C "$REPO_DIR" rev-parse HEAD)" == "$(git -C "$REPO_DIR" rev-parse origin/master)" ]] \
  || { echo "master entspricht nicht origin/master" >&2; exit 1; }
COMMIT="$(git -C "$REPO_DIR" rev-parse --short HEAD)"
VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$SRC/manifest.json")"

case "$MODE" in
  zip)
    mkdir -p "$REPO_DIR/dist"
    OUT="$REPO_DIR/dist/${DOMAIN}-${VERSION}-${COMMIT}.zip"
    rm -f "$OUT"
    # Aus dem Git-Stand bauen, nicht aus der Arbeitskopie (keine __pycache__ o. ae.)
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    git -C "$REPO_DIR" archive HEAD "custom_components/$DOMAIN" | tar -x -C "$TMP"
    (cd "$TMP/custom_components" && zip -qrX "$OUT" "$DOMAIN")
    echo "Gebaut: $OUT"
    sha256sum "$OUT"
    ;;
  *)
    echo "Aufruf: $0 zip" >&2
    exit 1
    ;;
esac
