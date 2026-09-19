#!/usr/bin/env sh
set -eu
python3 -m pip install -e .
continuity install --agents claude,codex
continuity doctor
