#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${TARGET_DIR:-}"
R2_REMOTE="${R2_REMOTE:-}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
RCLONE_FLAGS="${RCLONE_FLAGS:-}"

if [[ -z "${TARGET_DIR}" || -z "${R2_REMOTE}" ]]; then
  echo "Usage: TARGET_DIR=/path/to/downloads R2_REMOTE=remote:bucket/inbox $0" >&2
  exit 2
fi

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "TARGET_DIR does not exist: ${TARGET_DIR}" >&2
  exit 2
fi

command -v rclone >/dev/null 2>&1 || {
  echo "rclone is required but was not found on PATH" >&2
  exit 2
}

rclone copy "${TARGET_DIR}" "${R2_REMOTE}" \
  --ignore-existing \
  --transfers 4 \
  --checkers 8 \
  ${RCLONE_FLAGS}

# Only prune after a successful upload pass. Files exactly 14 days old are kept
# until the next run; files older than that are removed from the personal machine.
find "${TARGET_DIR}" -type f -mtime +"${RETENTION_DAYS}" -delete
