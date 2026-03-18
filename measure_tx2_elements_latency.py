#!/usr/bin/env python3

"""Use `GST_DEBUG_NO_COLOR=1 GST_DEBUG="GST_TRACER:7" GST_TRACERS="proctime" app 2> log.txt` to generate the input log for this tool """

import argparse
import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


LOG_PATTERN = re.compile(
    r"GST_TRACER\s*:\d*::\s*proctime,\s*element=\(string\)(?P<element>[^,]+),\s*time=\(string\)(?P<time>\d+:\d+:\d+\.\d+);"
)


def parse_gst_time(raw_value):
    hours_str, minutes_str, seconds_str = raw_value.split(":")
    hours = int(hours_str)
    minutes = int(minutes_str)
    seconds = float(seconds_str)
    return (hours * 3600.0) + (minutes * 60.0) + seconds


def iter_lines(paths):
    if not paths:
        for line in sys.stdin:
            yield line
        return

    for path in paths:
        with open(str(path), "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line


def parse_samples(lines):
    samples = []

    for line in lines:
        match = LOG_PATTERN.search(line)
        if not match:
            continue

        element = match.group("element").strip()
        seconds = parse_gst_time(match.group("time"))
        samples.append((element, seconds))

    return samples


def build_stats(samples):
    stats = defaultdict(list)

    for element, seconds in samples:
        stats[element].append(seconds)

    return stats


def make_summary(element, values):
    count = len(values)
    total = sum(values)
    average = statistics.mean(values) if values else 0.0
    maximum = max(values) if values else 0.0

    return {
        "element": element,
        "count": count,
        "avg_s": average,
        "max_s": maximum,
        "total_s": total,
    }


def sort_summaries(summaries):
    return sorted(summaries, key=lambda item: item["avg_s"], reverse=True)


def print_header(total_samples, distinct_elements):
    print("")
    print("GStreamer proctime summary")
    print("=" * 95)
    print("Samples:           {}".format(total_samples))
    print("Distinct elements: {}".format(distinct_elements))
    print("=" * 95)
    print("")


def print_table(summaries):
    header = "{:<40} {:>10} {:>15} {:>15} {:>15}".format(
        "Element", "Count", "Avg ms", "Max ms", "Total ms"
    )
    print(header)
    print("-" * len(header))

    for item in summaries:
        print(
            "{:<40} {:>10} {:>15.3f} {:>15.3f} {:>15.3f}".format(
                item["element"][:40],
                item["count"],
                item["avg_s"] * 1000.0,
                item["max_s"] * 1000.0,
                item["total_s"] * 1000.0,
            )
        )

    print("")


def export_csv(summaries, output_path):
    fieldnames = [
        "element",
        "count",
        "avg_ms",
        "max_ms",
        "total_ms",
    ]

    with open(str(output_path), "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for item in summaries:
            writer.writerow(
                {
                    "element": item["element"],
                    "count": item["count"],
                    "avg_ms": item["avg_s"] * 1000.0,
                    "max_ms": item["max_s"] * 1000.0,
                    "total_ms": item["total_s"] * 1000.0,
                }
            )


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description="Summarize GStreamer GST_TRACER proctime logs."
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Log files to parse. If omitted, stdin is used.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Export the aggregated summary as CSV.",
    )
    return parser


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    lines = iter_lines(args.files)
    samples = parse_samples(lines)

    if not samples:
        print("No GST_TRACER proctime samples were found.", file=sys.stderr)
        return 1

    stats_by_element = build_stats(samples)
    summaries = []

    for element, values in stats_by_element.items():
        summaries.append(make_summary(element, values))

    sorted_summaries = sort_summaries(summaries)

    print_header(total_samples=len(samples), distinct_elements=len(stats_by_element))
    print_table(sorted_summaries)

    if args.csv:
        export_csv(sorted_summaries, args.csv)
        print("CSV written to: {}".format(args.csv))

    return 0


if __name__ == "__main__":
    sys.exit(main())
