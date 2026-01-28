#!/usr/bin/env bash

set -euo pipefail



# Usage:

#   ./stack3.sh in1.mp4 in2.mp4 in3.mp4 out.mp4

#

# Layout (1920x1080):

#   top row:    [in1  960x540] [in2  960x540]

#   bottom row:        [in3  960x540] centered

#

# Behavior:

#   Output ends as soon as ANY of the three videos hits EOF.



if [[ $# -ne 4 ]]; then

  echo "Usage: $0 <video1> <video2> <video3> <out>"

  exit 1

fi



v1="$1"

v2="$2"

v3="$3"

out="$4"



ffmpeg -hide_banner -y \

  -i "$v1" -i "$v2" -i "$v3" \

  -filter_complex "

    [0:v]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];

    [1:v]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1[v2];

    [2:v]scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1[v3];



    color=c=black:s=1920x1080:r=30[base];



    [base][v1]overlay=0:0:eof_action=endall[tmp1];

    [tmp1][v2]overlay=960:0:eof_action=endall[tmp2];

    [tmp2][v3]overlay=(W-w)/2:540:eof_action=endall[v]

  " \

  -map "[v]" \

  -map 0:a? -map 1:a? -map 2:a? \

  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset veryfast \

  -c:a aac -b:a 192k \

  -shortest \

  "$out"
