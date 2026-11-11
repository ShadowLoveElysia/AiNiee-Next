#!/usr/bin/env sh
set -eu

case "${AINIEE_SERVICE:-cli}" in
  cli)
    exec uv run ainiee_cli.py "$@"
    ;;
  skills)
    exec uv run python Tools/Skills/server.py \
      --host "${AINIEE_SKILLS_HOST:-0.0.0.0}" \
      --port "${AINIEE_SKILLS_PORT:-8766}" \
      --allow-remote-access \
      "$@"
    ;;
  *)
    echo "[ERROR] Unsupported AINIEE_SERVICE: ${AINIEE_SERVICE}" >&2
    echo "[ERROR] Expected one of: cli, skills" >&2
    exit 2
    ;;
esac
