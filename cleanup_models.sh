#!/bin/bash
# ============================================================
#  SEEMA DRISHTI — Model Cleanup Script
#  Removes all downloaded AI model files to free disk space.
#  Run this AFTER you are done with the project.
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo -e "${CYAN}${BOLD}  SEEMA DRISHTI — AI Model Cleanup Script${NC}"
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo ""

TOTAL_FREED=0

# Helper function to remove a path and report size
remove_path() {
    local label="$1"
    local path="$2"

    if [ -e "$path" ]; then
        SIZE=$(du -sh "$path" 2>/dev/null | awk '{print $1}')
        echo -e "  ${YELLOW}→ Removing:${NC} $label"
        echo -e "    Path: ${path}"
        echo -e "    Size freed: ${RED}${SIZE}${NC}"
        rm -rf "$path"
        echo -e "    ${GREEN}✓ Deleted${NC}"
        echo ""
    else
        echo -e "  ${GREEN}✓ Already clean:${NC} $label (not found)"
        echo ""
    fi
}

echo -e "${BOLD}── External Model Caches (outside project) ──────────────────${NC}"
echo ""

# InsightFace
remove_path "InsightFace buffalo_s (face recognition)" "$HOME/.insightface"

# DeepFace
remove_path "DeepFace weights (face detection/recognition)" "$HOME/.deepface"

# Ultralytics cache
remove_path "Ultralytics model cache" "$HOME/.cache/ultralytics"


echo -e "${BOLD}── Project-Level Model Files ────────────────────────────────${NC}"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# YOLOv8 nano
remove_path "YOLOv8n (object detection)" "$PROJECT_DIR/yolov8n.pt"

# YOLOv8s TensorRT engine
remove_path "YOLOv8s TensorRT Engine" "$PROJECT_DIR/yolov8s.engine"

# Ultralytics weights folder
remove_path "Ultralytics weights dir" "$PROJECT_DIR/weights"

# Custom human detection model
remove_path "Custom border human detection model" "$PROJECT_DIR/human_detection/models"

# YOLO training runs
remove_path "YOLO training runs/logs" "$PROJECT_DIR/runs"


echo -e "${BOLD}── Checking for any remaining .pt / .h5 / .onnx files ───────${NC}"
echo ""

REMAINING=$(find "$PROJECT_DIR" -not -path "*/venv/*" -not -path "*/.git/*" \
    \( -name "*.pt" -o -name "*.h5" -o -name "*.onnx" -o -name "*.caffemodel" \) \
    2>/dev/null)

if [ -n "$REMAINING" ]; then
    echo -e "  ${YELLOW}⚠ Found leftover model files:${NC}"
    echo "$REMAINING" | while read -r f; do
        SIZE=$(du -sh "$f" 2>/dev/null | awk '{print $1}')
        echo -e "    ${RED}[$SIZE]${NC} $f"
    done
    echo ""
    read -rp "  Delete all of the above? (y/N): " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "$REMAINING" | xargs rm -f
        echo -e "  ${GREEN}✓ Deleted all remaining model files.${NC}"
    else
        echo -e "  ${YELLOW}Skipped.${NC}"
    fi
else
    echo -e "  ${GREEN}✓ No remaining model files found inside project.${NC}"
fi

echo ""
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD}  ✅ Cleanup complete! Storage reclaimed.${NC}"
echo -e "${CYAN}${BOLD}============================================================${NC}"
echo ""
echo -e "  ${YELLOW}Note:${NC} The project code itself was NOT deleted."
echo -e "  To fully delete the project:"
echo -e "  ${RED}  rm -rf \"$PROJECT_DIR\"${NC}"
echo ""
