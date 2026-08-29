#!/bin/zsh
set -e

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR"
export CHECKPOINT_SCRIPTED_FALLBACK=force
exec python3 server.py
