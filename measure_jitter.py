#!/usr/bin/env python3

import os
import re
import time
import signal
import subprocess
import argparse

JITTER_RE = re.compile(
    r"<([^>]+)>.*jitter\s+(-?)\s*(\d+):(\d+):(\d+)\.(\d+)"
)

def parse_ns(match):
    sign = match.group(2)

    ns = (
        int(match.group(3)) * 3600 * 1000000000 +
        int(match.group(4)) * 60 * 1000000000 +
        int(match.group(5)) * 1000000000 +
        int(match.group(6).ljust(9, "0")[:9])
    )

    if sign == "-":
        ns = -ns

    return ns

def ns_to_ms(ns):
    return ns / 1000000.0

def print_stats(total, positive, negative, sum_ns, min_ns, max_ns, last_ns):
    if total == 0:
        return

    avg_ns = sum_ns / float(total)

    print(
        "samples={} | positive={} ({:.2f}%) | negative={} ({:.2f}%) | "
        "avg={:.3f} ms | min={:.3f} ms | max={:.3f} ms | last={:.3f} ms".format(
            total,
            positive,
            positive * 100.0 / total,
            negative,
            negative * 100.0 / total,
            ns_to_ms(avg_ns),
            ns_to_ms(min_ns),
            ns_to_ms(max_ns),
            ns_to_ms(last_ns),
        )
    )

def stop_process_group(process):
    if process.poll() is not None:
        return

    pgid = os.getpgid(process.pid)

    os.killpg(pgid, signal.SIGINT)
    time.sleep(1)

    if process.poll() is None:
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(1)

    if process.poll() is None:
        os.killpg(pgid, signal.SIGKILL)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--rate-window", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=60.0,
                        help="Test duration in seconds (default 60)")
    parser.add_argument("--script", default="./testing.sh")
    args = parser.parse_args()

    process = subprocess.Popen(
        ["bash", args.script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        preexec_fn=os.setsid
    )

    total = 0
    positive = 0
    negative = 0
    sum_ns = 0
    min_ns = None
    max_ns = None
    last_ns = 0

    rate_pos = 0
    rate_neg = 0
    rate_start = time.time()

    start_time = time.time()
    last_print = time.time()

    try:
        for line in process.stdout:

            now = time.time()

            # ⛔ cortar por duración
            if now - start_time >= args.duration:
                print("\nReached duration limit ({}s)".format(args.duration))
                break

            if "jitter" not in line or "bev_fisheye_channel" not in line:
                continue

            match = JITTER_RE.search(line)
            if not match:
                continue

            jitter_ns = parse_ns(match)
            last_ns = jitter_ns

            total += 1
            sum_ns += jitter_ns

            if jitter_ns > 0:
                positive += 1
                rate_pos += 1
            elif jitter_ns < 0:
                negative += 1
                rate_neg += 1

            if min_ns is None or jitter_ns < min_ns:
                min_ns = jitter_ns

            if max_ns is None or jitter_ns > max_ns:
                max_ns = jitter_ns

            # print stats
            if now - last_print >= args.interval:
                print_stats(total, positive, negative, sum_ns, min_ns, max_ns, last_ns)
                last_print = now

            # rate window
            if now - rate_start >= args.rate_window:
                print(
                    "pos_rate / {:.0f}s = {}, neg_rate / {:.0f}s = {}".format(
                        args.rate_window,
                        rate_pos,
                        args.rate_window,
                        rate_neg
                    )
                )

                rate_pos = 0
                rate_neg = 0
                rate_start = now

    except KeyboardInterrupt:
        pass

    finally:
        stop_process_group(process)

        print("\nFinal result:")
        print_stats(total, positive, negative, sum_ns, min_ns, max_ns, last_ns)


if __name__ == "__main__":
    main()
