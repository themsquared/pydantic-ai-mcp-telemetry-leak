#!/usr/bin/env bash
# Runs scripts/repro_leak.py unmodified against the vulnerable release
# (2.56.0) and the fixed release (2.58.0), so the diff is the proof.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== pydantic-ai-slim 2.56.0 (vulnerable) ==="
rm -rf .venv-vuln
python3 -m venv .venv-vuln
.venv-vuln/bin/pip install -q --upgrade pip
.venv-vuln/bin/pip install -q "pydantic-ai-slim[mcp,anthropic]==2.56.0" opentelemetry-sdk
.venv-vuln/bin/python3 scripts/repro_leak.py
echo

echo "=== pydantic-ai-slim 2.58.0 (fixed) ==="
rm -rf .venv-fixed
python3 -m venv .venv-fixed
.venv-fixed/bin/pip install -q --upgrade pip
.venv-fixed/bin/pip install -q "pydantic-ai-slim[mcp,anthropic]==2.58.0" opentelemetry-sdk
.venv-fixed/bin/python3 scripts/repro_leak.py
