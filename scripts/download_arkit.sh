#!/usr/bin/env bash
# Download ARKitScenes assets needed by this project.
# Usage:
#   bash scripts/download_arkit.sh annotations            # step 1: annotations of all Validation videos (small)
#   bash scripts/download_arkit.sh frames data/selected_scenes.csv   # step 2: frames for the selected scenes
# Requires: git, curl, unzip, python3 (or set PYTHON). Read and accept the ARKitScenes license first:
#   https://github.com/apple/ARKitScenes/blob/main/LICENSE  (non-commercial research use)
set -euo pipefail
PY="${PYTHON:-python3}"   # override on Windows, e.g. PYTHON=.venv/Scripts/python.exe
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARK="$ROOT/third_party/ARKitScenes"
OUT="$ROOT/data/arkitscenes"
[ -d "$ARK" ] || git clone --depth 1 https://github.com/apple/ARKitScenes.git "$ARK"
mkdir -p "$OUT"
case "${1:-}" in
  annotations)
    # all Validation video ids of the 3DOD subset
    "$PY" - "$ARK/threedod/3dod_train_val_splits.csv" "$OUT/val_ids.csv" <<'PY'
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1])) if r["fold"] == "Validation"]
with open(sys.argv[2], "w", newline="") as f:
    w = csv.writer(f); w.writerow(["video_id", "fold"])
    for r in rows: w.writerow([r["video_id"], "Validation"])
print(len(rows), "validation videos")
PY
    "$PY" "$ARK/download_data.py" raw --video_id_csv "$OUT/val_ids.csv" --download_dir "$OUT" \
      --raw_dataset_assets annotation
    ;;
  frames)
    CSV="${2:?give the csv written by scripts/select_scenes.py}"
    "$PY" "$ARK/download_data.py" raw --video_id_csv "$CSV" --download_dir "$OUT" \
      --raw_dataset_assets lowres_wide.traj vga_wide vga_wide_intrinsics lowres_depth lowres_wide_intrinsics annotation
    ;;
  *) echo "usage: $0 annotations | frames <csv>"; exit 1;;
esac
