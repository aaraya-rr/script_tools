# script_tools

Utility scripts for Jetson profiling and simple video layout generation.

## Scripts

### `measure_jetson`

Profiles Jetson CPU, GPU, and RAM usage from `tegrastats` for a fixed duration.

- Language: Python 3
- Inputs: measurement duration in seconds
- Outputs:
  - PDF report
  - Optional intermediate `.log` and per-metric `.csv` files
  - Console summary in `--quick` mode

Dependencies:

- `tegrastats`
- Python 3
- Python package: `matplotlib`
- Optional system tools for extra report metadata: `nvcc`, `deepstream-app`

Usage:

```bash
./measure_jetson <duration_seconds> [--interval-ms N] [--output-dir DIR] [--keep-intermediate] [--quick]
```

Examples:

```bash
./measure_jetson 60
./measure_jetson 120 --interval-ms 500 --output-dir reports
./measure_jetson 30 --quick
```

Notes:

- The generated base name is `tegrastats_<timestamp>_dur<duration>s`.
- Without `--keep-intermediate`, the script deletes the raw log and CSV files after the PDF is generated.
- `--quick` skips all file output and prints aggregate metrics only.

### `measure_jetson_temperature`

Monitors Jetson temperature sensors from `tegrastats` with live terminal bars and produces temperature artifacts.

- Language: Python 3
- Inputs:
  - live `tegrastats` output, or
  - stdin when `--stdin` is used
- Outputs:
  - PDF chart
  - Graphviz `.dot`
  - final text summary `.txt`
  - Optional copied `.csv` and raw `.log` with `--keep`

Dependencies:

- `tegrastats`
- `nvpmodel`
- Python 3
- Python package: `matplotlib`
- Optional: Graphviz `neato` if you want to render the `.dot` file separately

Usage:

```bash
./measure_jetson_temperature [--duration N] [--until-q] [--stable-sensor NAME] [--stable-seconds N] [--stable-delta C] [--interval-ms N] [--output-dir DIR] [--output-prefix NAME] [--keep]
```

Examples:

```bash
./measure_jetson_temperature --duration 60
./measure_jetson_temperature --stable-sensor tj --stable-seconds 90
./measure_jetson_temperature --until-q --keep
tegrastats --interval 1000 | ./measure_jetson_temperature --stdin --duration 30
```

Notes:

- If no stop mode is specified, it defaults to `--until-q`.
- Stability mode stops after the selected sensor stays below its last maximum plus `--stable-delta` for `--stable-seconds`.
- Output files default to `tegrastats_<timestamp>.<ext>` in the selected output directory.
- Temporary raw files are kept only when `--keep` is set.

### `side_by_side.sh`

Builds an `N`-video grid with labels using `ffmpeg` `xstack`.

- Language: Bash
- Inputs: 2 or more video files
- Output: a single MP4 grid composition

Dependencies:

- `ffmpeg`
- `python3` for automatic square-root grid sizing

Usage:

```bash
./side_by_side.sh [options] <video1> <video2> [video3 ... videoN]
```

Supported options:

- `-o, --output FILE`: output file, default `out_grid.mp4`
- `--cols N`: fixed number of columns
- `--rows N`: fixed number of rows
- `--cell-w W`: cell width, default `960`
- `--cell-h H`: cell height, default `540`
- `--fps F`: output FPS
- `--crf V`: x264 CRF, default `18`
- `--preset P`: x264 preset, default `medium`
- `--labels "A|B|C"`: custom labels separated by `|`
- `--font FILE`: custom TTF/OTF font
- `--fontsize PX`: fixed label font size
- `--no-box`: disable the label background box

Examples:

```bash
./side_by_side.sh --cols 1 a.mp4 b.mp4
./side_by_side.sh --cols 2 --cell-w 1280 --cell-h 720 --fps 30 a.mp4 b.mp4 c.mp4 d.mp4
./side_by_side.sh --labels "Baseline|Tracker" run1.mp4 run2.mp4
```

Notes:

- When neither `--cols` nor `--rows` is provided, layout is computed automatically from `sqrt(N)`.
- Labels default to the input filenames without extensions.
- The script maps video from the generated grid and audio from the first input only with `-map 0:a?`.

### `side_by_side_3_videos.sh`

Creates a fixed 3-video layout:

- top-left: video 1 scaled into `960x540`
- top-right: video 2 scaled into `960x540`
- bottom-center: video 3 scaled into `960x540`

Dependencies:

- `ffmpeg`

Usage:

```bash
./side_by_side_3_videos.sh <video1> <video2> <video3> <out>
```

Example:

```bash
./side_by_side_3_videos.sh cam1.mp4 cam2.mp4 cam3.mp4 combined.mp4
```

Notes:

- Output canvas is `1920x1080` at 30 FPS.
- The render stops as soon as any input video reaches EOF because the overlays use `eof_action=endall`.
- Audio from all three inputs is mapped when present.

## Setup

Install the runtime pieces you need for the scripts you plan to use.

```bash
python3 -m pip install matplotlib
```

System tools expected by these scripts include:

- `ffmpeg`
- `tegrastats`
- `nvpmodel`

## Repository Layout

```text
.
├── measure_jetson
├── measure_jetson_temperature
├── side_by_side.sh
└── side_by_side_3_videos.sh
```
