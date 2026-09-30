#!/usr/bin/env bash
# Clone the paper's public release (dataset + notebooks) into third_party/. It has no licence file:
# private research use only, never commit or re-upload its images.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -d "$ROOT/third_party/SDA-LLM" ] || git clone --depth 1 https://github.com/CKL9001/SDA-LLM.git "$ROOT/third_party/SDA-LLM"
git -C "$ROOT/third_party/SDA-LLM" log -1 --format='release commit %h (%cd)'
