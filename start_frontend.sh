#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python -m streamlit run frontend/app.py --server.port 8501
