#!/usr/bin/env python3

"""Use `GST_DEBUG_NO_COLOR=1 GST_DEBUG="GST_TRACER:7" GST_TRACERS="proctime" app 2> log.txt` to generate the input log for this tool """

import argparse
import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


LOG_PATTERN = re.compile(
    r"GST_TRACER\s*:\d*::\s*proctime,\s*element=\(string\)(?P<element>[^,]+),\s*time=\(string\)(?P<time>\d+:\d+:\d+\.\d+);"
)


def percentile(values, q):
    if not values:
        return 0.0

    if q <= 0.0:
        return min(values)

    if q >= 100.0:
        return max(values)

    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * (q / 100.0)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))

    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    fraction = position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


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


def parse_samples(lines, include_pattern=None, exclude_pattern=None):
    include_regex = re.compile(include_pattern) if include_pattern else None
    exclude_regex = re.compile(exclude_pattern) if exclude_pattern else None

    samples = []

    for line in lines:
        match = LOG_PATTERN.search(line)
        if not match:
            continue

        element = match.group("element").strip()

        if include_regex and not include_regex.search(element):
            continue

        if exclude_regex and exclude_regex.search(element):
            continue

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
    minimum = min(values) if values else 0.0
    maximum = max(values) if values else 0.0
    median = percentile(values, 50.0)
    p90 = percentile(values, 90.0)
    p95 = percentile(values, 95.0)
    p99 = percentile(values, 99.0)

    if count >= 2:
        stddev = statistics.pstdev(values)
    else:
        stddev = 0.0

    jitter_ratio = (stddev / average) if average > 0.0 else 0.0

    return {
        "element": element,
        "count": count,
        "total_s": total,
        "avg_s": average,
        "min_s": minimum,
        "median_s": median,
        "p90_s": p90,
        "p95_s": p95,
        "p99_s": p99,
        "max_s": maximum,
        "stddev_s": stddev,
        "jitter_ratio": jitter_ratio,
    }


def sort_summaries(summaries, sort_by):
    key_map = {
        "total": lambda x: x["total_s"],
        "avg": lambda x: x["avg_s"],
        "max": lambda x: x["max_s"],
        "p95": lambda x: x["p95_s"],
        "p99": lambda x: x["p99_s"],
        "count": lambda x: x["count"],
        "stddev": lambda x: x["stddev_s"],
        "jitter": lambda x: x["jitter_ratio"],
    }

    return sorted(summaries, key=key_map[sort_by], reverse=True)


def print_header(total_samples, distinct_elements):
    print("")
    print("GStreamer proctime summary")
    print("=" * 110)
    print("Samples:           {}".format(total_samples))
    print("Distinct elements: {}".format(distinct_elements))
    print("=" * 110)
    print("")


def print_table(summaries, limit):
    header = "{:<32} {:>8} {:>10} {:>10} {:>10} {:>10} {:>12} {:>8}".format(
        "Element", "Count", "Avg ms", "P95 ms", "P99 ms", "Max ms", "Total ms", "Jitter"
    )
    print(header)
    print("-" * len(header))

    for item in summaries[:limit]:
        print(
            "{:<32} {:>8} {:>10.3f} {:>10.3f} {:>10.3f} {:>10.3f} {:>12.3f} {:>8.3f}".format(
                item["element"][:32],
                item["count"],
                item["avg_s"] * 1000.0,
                item["p95_s"] * 1000.0,
                item["p99_s"] * 1000.0,
                item["max_s"] * 1000.0,
                item["total_s"] * 1000.0,
                item["jitter_ratio"],
            )
        )

    print("")


def print_bottleneck_candidates(summaries, limit):
    print("Potential bottlenecks")
    print("-" * 110)

    for index, item in enumerate(summaries[:limit], start=1):
        reasons = []

        if item["avg_s"] >= 0.010:
            reasons.append("high average")
        if item["p95_s"] >= 0.016:
            reasons.append("high p95")
        if item["max_s"] >= 0.033:
            reasons.append("high max")
        if item["jitter_ratio"] >= 0.50:
            reasons.append("high jitter")

        if not reasons:
            reasons.append("top-ranked by selected metric")

        print(
            "{:2d}. {:<32} avg={:.3f} ms, p95={:.3f} ms, max={:.3f} ms, reasons={}".format(
                index,
                item["element"][:32],
                item["avg_s"] * 1000.0,
                item["p95_s"] * 1000.0,
                item["max_s"] * 1000.0,
                ", ".join(reasons),
            )
        )

    print("")


def print_single_element_details(stats_by_element, element_name):
    if element_name not in stats_by_element:
        print("Element '{}' was not found.".format(element_name), file=sys.stderr)
        return

    item = make_summary(element_name, stats_by_element[element_name])

    print("Details for element: {}".format(element_name))
    print("-" * 110)
    for key in [
        "element",
        "count",
        "total_s",
        "avg_s",
        "min_s",
        "median_s",
        "p90_s",
        "p95_s",
        "p99_s",
        "max_s",
        "stddev_s",
        "jitter_ratio",
    ]:
        value = item[key]
        if isinstance(value, float):
            print("{:<16}: {:.6f}".format(key, value))
        else:
            print("{:<16}: {}".format(key, value))
    print("")


def export_csv(summaries, output_path):
    fieldnames = [
        "element",
        "count",
        "total_ms",
        "avg_ms",
        "min_ms",
        "median_ms",
        "p90_ms",
        "p95_ms",
        "p99_ms",
        "max_ms",
        "stddev_ms",
        "jitter_ratio",
    ]

    with open(str(output_path), "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for item in summaries:
            writer.writerow(
                {
                    "element": item["element"],
                    "count": item["count"],
                    "total_ms": item["total_s"] * 1000.0,
                    "avg_ms": item["avg_s"] * 1000.0,
                    "min_ms": item["min_s"] * 1000.0,
                    "median_ms": item["median_s"] * 1000.0,
                    "p90_ms": item["p90_s"] * 1000.0,
                    "p95_ms": item["p95_s"] * 1000.0,
                    "p99_ms": item["p99_s"] * 1000.0,
                    "max_ms": item["max_s"] * 1000.0,
                    "stddev_ms": item["stddev_s"] * 1000.0,
                    "jitter_ratio": item["jitter_ratio"],
                }
            )


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description="Analyze GStreamer GST_TRACER proctime logs and identify bottlenecks."
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Log files to parse. If omitted, stdin is used.",
    )
    parser.add_argument(
        "--sort-by",
        choices=["total", "avg", "max", "p95", "p99", "count", "stddev", "jitter"],
        default="p95",
        help="Metric used to sort the summary table.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of rows to display.",
    )
    parser.add_argument(
        "--include",
        type=str,
        default=None,
        help="Regex used to include only matching element names.",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="Regex used to exclude matching element names.",
    )
    parser.add_argument(
        "--element",
        type=str,
        default=None,
        help="Show a detailed summary for a single element.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Export the aggregated stats as CSV.",
    )
    return parser


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    lines = iter_lines(args.files)
    samples = parse_samples(
        lines=lines,
        include_pattern=args.include,
        exclude_pattern=args.exclude,
    )

    if not samples:
        print("No GST_TRACER proctime samples were found.", file=sys.stderr)
        return 1

    stats_by_element = build_stats(samples)
    summaries = []

    for element, values in stats_by_element.items():
        summaries.append(make_summary(element, values))

    sorted_summaries = sort_summaries(summaries, args.sort_by)

    print_header(total_samples=len(samples), distinct_elements=len(stats_by_element))
    print_table(sorted_summaries, args.top)
    print_bottleneck_candidates(sorted_summaries, min(args.top, 10))

    if args.element:
        print_single_element_details(stats_by_element, args.element)

    if args.csv:
        export_csv(sorted_summaries, args.csv)
        print("CSV written to: {}".format(args.csv))

    return 0


if __name__ == "__main__":
    sys.exit(main())
