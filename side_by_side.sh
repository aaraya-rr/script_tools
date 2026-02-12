#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  grid_stack.sh [options] <video1> <video2> [video3 ... videoN]

Options:
  -o, --output FILE         Output file (default: out_grid.mp4)
  --cols N                  Number of columns (if omitted, auto ~sqrt(N))
  --rows N                  Number of rows (alternative to --cols; if both omitted, auto)
  --cell-w W                Cell width  (default: 960)
  --cell-h H                Cell height (default: 540)  # standard 16:9
  --fps F                   Output FPS (optional)
  --crf V                   x264 CRF (default: 18)
  --preset P                x264 preset (default: medium)
  --labels "A|B|C|..."      Custom labels per video (separated by '|')
  --font FILE               Path to TTF/OTF font (tries DejaVuSans-Bold by default)
  --fontsize PX             Fixed font size (default: proportional to --cell-w)
  --no-box                  Disable label box background (enabled by default)
  -h, --help                Show this help

Examples:
  # 2 videos vertical (2 rows, 1 column), default labels (filename)
  grid_stack.sh --cols 1 a.mp4 b.mp4

  # Auto-layout (√N), custom labels
  grid_stack.sh --labels "No Tracker|Tracker probationAge: 4, earlyTerminationAge: 10" a.mp4 b.mp4

  # 4 videos in 2x2, 1280x720 cells, 30fps output
  grid_stack.sh --cols 2 --cell-w 1280 --cell-h 720 --fps 30 a.mp4 b.mp4 c.mp4 d.mp4
EOF
}

# Defaults
OUT="out_grid.mp4"
COLS=""
ROWS=""
CELL_W=960
CELL_H=540
FPS=""
CRF=18
PRESET="medium"
LABELS_ARG=""
FONT_CAND="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTSIZE=""
BOX=1

# Parse args
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUT="$2"; shift 2;;
    --cols) COLS="$2"; shift 2;;
    --rows) ROWS="$2"; shift 2;;
    --cell-w) CELL_W="$2"; shift 2;;
    --cell-h) CELL_H="$2"; shift 2;;
    --fps) FPS="$2"; shift 2;;
    --crf) CRF="$2"; shift 2;;
    --preset) PRESET="$2"; shift 2;;
    --labels) LABELS_ARG="$2"; shift 2;;
    --font) FONT_CAND="$2"; shift 2;;
    --fontsize) FONTSIZE="$2"; shift 2;;
    --no-box) BOX=0; shift;;
    -h|--help) usage; exit 0;;
    --) shift; while [[ $# -gt 0 ]]; do ARGS+=("$1"); shift; done; break;;
    -*)
      echo "Unknown option: $1"
      usage; exit 1;;
    *)
      ARGS+=("$1"); shift;;
  esac
done

if [[ ${#ARGS[@]} -lt 2 ]]; then
  echo "At least 2 input videos are required."
  usage
  exit 1
fi

# Validate input files
for f in "${ARGS[@]}"; do
  [[ -f "$f" ]] || { echo "File not found: $f"; exit 1; }
done

N=${#ARGS[@]}

# Grid helpers
int_ceil_div() { # ceil(a/b)
  local a=$1 b=$2
  echo $(( (a + b - 1) / b ))
}

# Determine grid
if [[ -n "$COLS" && -n "$ROWS" ]]; then
  :
elif [[ -n "$COLS" ]]; then
  ROWS=$(int_ceil_div "$N" "$COLS")
elif [[ -n "$ROWS" ]]; then
  COLS=$(int_ceil_div "$N" "$ROWS")
else
  # Auto: approx sqrt(N) => cols = ceil(sqrt(N)); rows = ceil(N/cols)
  sq=$(python3 - <<PY
import math; N=${N}
c=math.ceil(math.sqrt(N)); r=math.ceil(N/c)
print(c, r)
PY
)
  COLS=$(echo "$sq" | awk '{print $1}')
  ROWS=$(echo "$sq" | awk '{print $2}')
fi

TOTAL_CELLS=$(( COLS * ROWS ))
if [[ "$N" -gt "$TOTAL_CELLS" ]]; then
  echo "Grid ${COLS}x${ROWS} is too small for ${N} videos."
  exit 1
fi

GRID_W=$(( COLS * CELL_W ))
GRID_H=$(( ROWS * CELL_H ))

# Labels
IFS='|' read -r -a USER_LABELS <<< "${LABELS_ARG:-}"
declare -a LABELS
for i in $(seq 0 $((N-1))); do
  if [[ $i -lt ${#USER_LABELS[@]} && -n "${USER_LABELS[$i]}" ]]; then
    LABELS[$i]="${USER_LABELS[$i]}"
  else
    base="$(basename -- "${ARGS[$i]}")"
    LABELS[$i]="${base%.*}"
  fi
done

# Escape text for drawtext
escape_dt() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//:/\\:}"
  s="${s//,/\\,}"
  s="${s//\'/\\\'}"
  echo "$s"
}

# Font options
if [[ -f "$FONT_CAND" ]]; then
  FONT_OPT="fontfile='${FONT_CAND}':"
else
  FONT_OPT=""  # will use fontconfig
fi

# Font size
if [[ -n "$FONTSIZE" ]]; then
  FS="$FONTSIZE"
else
  FS=$(( CELL_W / 30 ))
  [[ $FS -lt 22 ]] && FS=22
fi

# Label box
if [[ "$BOX" -eq 1 ]]; then
  BOX_OPT="box=1:boxcolor=black@0.6:boxborderw=10"
else
  BOX_OPT="box=0"
fi

# Build filter_complex for each input
FILTER=""
for i in $(seq 0 $((N-1))); do
  lbl="$(escape_dt "${LABELS[$i]}")"
  FILTER+="
[${i}:v]scale=${CELL_W}:${CELL_H}:force_original_aspect_ratio=decrease,\
pad=${CELL_W}:${CELL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,\
drawtext=${FONT_OPT}text='${lbl}':x=10:y=10:fontsize=${FS}:fontcolor=white:${BOX_OPT}[v${i}];"
done

# xstack layout:
# If N is odd AND the last row has exactly one video (N % COLS == 1),
# place the last video centered on the bottom row, leaving black on both sides.
LAYOUT=""
for i in $(seq 0 $((N-1))); do
  r=$(( i / COLS ))
  c=$(( i % COLS ))

  x=$(( c * CELL_W ))
  y=$(( r * CELL_H ))

  if [[ $i -eq $((N-1)) ]]; then
    if (( (N % 2) == 1 )) && (( (N % COLS) == 1 )) && (( r == (ROWS-1) )); then
      x=$(( (GRID_W - CELL_W) / 2 ))
      y=$(( (ROWS-1) * CELL_H ))
    fi
  fi

  LAYOUT+="${x}_${y}|"
done
LAYOUT="${LAYOUT%|}"

FILTER+="
"
for i in $(seq 0 $((N-1))); do
  FILTER+="[v${i}]"
done

# Force xstack fill to black to avoid any green/uninitialized background.
FILTER+="xstack=inputs=${N}:layout=${LAYOUT}:fill=black[vout]"

# FPS optional
FPS_ARGS=()
if [[ -n "${FPS}" ]]; then
  FPS_ARGS=(-r "${FPS}")
fi

# Run ffmpeg
ffmpeg -hide_banner -y \
  $(for f in "${ARGS[@]}"; do printf -- "-i %q " "$f"; done) \
  -filter_complex "$FILTER" \
  -map "[vout]" -map 0:a? \
  -c:v libx264 -crf "${CRF}" -preset "${PRESET}" -pix_fmt yuv420p \
  "${FPS_ARGS[@]}" \
  -c:a aac -b:a 192k -shortest \
  "$OUT"

echo "✅ Generated: $OUT"

