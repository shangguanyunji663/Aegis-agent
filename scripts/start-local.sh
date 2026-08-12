#!/usr/bin/env bash
set -euo pipefail

python -m app.init_db
uvicorn app.main:app --host 127.0.0.1 --port 8091
