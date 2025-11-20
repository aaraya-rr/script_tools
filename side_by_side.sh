#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Uso:
  grid_stack.sh [opciones] <video1> <video2> [video3 ... videoN]

Opciones:
  -o, --output FILE         Salida (por defecto: out_grid.mp4)
  --cols N                  Número de columnas (si no se indica, se calcula automático ~sqrt(N))
  --rows N                  Número de filas (alternativo a --cols; si ambos se omiten, auto)
  --cell-w W                Ancho de cada celda (por defecto: 960)
  --cell-h H                Alto de cada celda  (por defecto: 540)  # 16:9 estándar
  --fps F                   FPS de salida (opcional)
  --crf V                   CRF x264 (por defecto: 18)
  --preset P                Preset x264 (por defecto: medium)
  --labels "A|B|C|..."      Etiquetas personalizadas por video (separadas por '|')
  --font FILE               Ruta a la fuente TTF/OTF (intenta DejaVuSans-Bold por defecto)
  --fontsize PX             Tamaño fijo de fuente (por defecto: proporcional a --cell-w)
  --no-box                  Desactiva fondo de caja del label (por defecto activado)
  -h, --help                Mostrar ayuda

Ejemplos:
  # 2 videos vertical (2 filas, 1 columna), labels por defecto (nombre de archivo)
  grid_stack.sh --cols 1 a.mp4 b.mp4

  # Auto-layout (√N), labels personalizados
  grid_stack.sh --labels "No Tracker|Tracker probationAge: 4, earlyTerminationAge: 10" a.mp4 b.mp4

  # 4 videos en 2x2, celdas 1280x720, salida 30fps
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

# Parse
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
      echo "Opción no reconocida: $1"
      usage; exit 1;;
    *)
      ARGS+=("$1"); shift;;
  esac
done

if [[ ${#ARGS[@]} -lt 2 ]]; then
  echo "Se requieren al menos 2 videos."; usage; exit 1;
fi

# Validar archivos
for f in "${ARGS[@]}"; do
  [[ -f "$f" ]] || { echo "No existe: $f"; exit 1; }
done

N=${#ARGS[@]}

# Determinar grid
int_ceil_div() { # ceil(a/b)
  local a=$1 b=$2
  echo $(( (a + b - 1) / b ))
}

if [[ -n "$COLS" && -n "$ROWS" ]]; then
  :
elif [[ -n "$COLS" ]]; then
  ROWS=$(int_ceil_div "$N" "$COLS")
elif [[ -n "$ROWS" ]]; then
  COLS=$(int_ceil_div "$N" "$ROWS")
else
  # Auto: aprox sqrt(N)
  # (pequeño heurístico: cols = ceil(sqrt(N)); rows = ceil(N/cols))
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
  echo "Grid ${COLS}x${ROWS} insuficiente para ${N} videos."
  exit 1
fi

# Preparar labels
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

# Escapar texto para drawtext
escape_dt() {
  # Escapa backslashes, colons, commas y apostrofes para drawtext
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
  FONT_OPT=""  # usará fontconfig
fi

# Font size
if [[ -n "$FONTSIZE" ]]; then
  FS="$FONTSIZE"
else
  # proporcional al ancho de celda (ej. 960 → ~32)
  FS=$(( CELL_W / 30 ))
  [[ $FS -lt 22 ]] && FS=22
fi

# Caja
if [[ "$BOX" -eq 1 ]]; then
  BOX_OPT="box=1:boxcolor=black@0.6:boxborderw=10"
else
  BOX_OPT="box=0"
fi

# Construir filter_complex:
# Para cada entrada:
#   [i:v]scale=w:h:force_original_aspect_ratio=decrease,
#        pad=CELL_W:CELL_H:(ow-iw)/2:(oh-ih)/2,
#        drawtext=...
#   => [v{i}]
FILTER=""
for i in $(seq 0 $((N-1))); do
  lbl="$(escape_dt "${LABELS[$i]}")"
  FILTER+="
[${i}:v]scale=${CELL_W}:${CELL_H}:force_original_aspect_ratio=decrease,\
pad=${CELL_W}:${CELL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,\
drawtext=${FONT_OPT}text='${lbl}':x=10:y=10:fontsize=${FS}:fontcolor=white:${BOX_OPT}[v${i}];"
done

# xstack layout
# layout requiere "x_y|x_y|..." para N entradas
LAYOUT=""
for i in $(seq 0 $((N-1))); do
  r=$(( i / COLS ))
  c=$(( i % COLS ))
  x=$(( c * CELL_W ))
  y=$(( r * CELL_H ))
  LAYOUT+="${x}_${y}|"
done
LAYOUT="${LAYOUT%|}"  # quitar último '|'

FILTER+="
"
# Conectar las etiquetas [v0][v1]...[vN-1]
for i in $(seq 0 $((N-1))); do
  FILTER+="[v${i}]"
done
FILTER+="xstack=inputs=${N}:layout=${LAYOUT}[vout]"

# FPS opcional
FPS_ARGS=()
if [[ -n "${FPS}" ]]; then
  FPS_ARGS=(-r "${FPS}")
fi

# Ejecutar ffmpeg
ffmpeg -hide_banner -y \
  $(for f in "${ARGS[@]}"; do printf -- "-i %q " "$f"; done) \
  -filter_complex "$FILTER" \
  -map "[vout]" -map 0:a? \
  -c:v libx264 -crf "${CRF}" -preset "${PRESET}" -pix_fmt yuv420p \
  "${FPS_ARGS[@]}" \
  -c:a aac -b:a 192k -shortest \
  "$OUT"

echo "✅ Generado: $OUT"
