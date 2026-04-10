import re
import argparse
from collections import defaultdict
from statistics import mean
from pathlib import Path


class TegrastatsParser:
    def __init__(self):
        self.metrics = defaultdict(list)

    def parse_line(self, line: str) -> None:
        if not line.strip():
            return

        self._parse_ram(line)
        self._parse_swap(line)
        self._parse_cpu(line)
        self._parse_freq(line)
        self._parse_temperatures(line)
        self._parse_power(line)

    # -------------------------
    # Parsers
    # -------------------------

    def _parse_ram(self, line: str) -> None:
        match = re.search(r"RAM (\d+)/(\d+)MB", line)
        if match:
            self.metrics["RAM_used_MB"].append(int(match.group(1)))
            self.metrics["RAM_total_MB"].append(int(match.group(2)))

    def _parse_swap(self, line: str) -> None:
        match = re.search(r"SWAP (\d+)/(\d+)MB", line)
        if match:
            self.metrics["SWAP_used_MB"].append(int(match.group(1)))
            self.metrics["SWAP_total_MB"].append(int(match.group(2)))

    def _parse_cpu(self, line: str) -> None:
        match = re.search(r"CPU \[(.*?)\]", line)
        if match:
            usages = []

            for core in match.group(1).split(","):
                usage_match = re.search(r"(\d+)%@", core)
                if usage_match:
                    usages.append(int(usage_match.group(1)))

            if usages:
                self.metrics["CPU_avg_percent"].append(mean(usages))
                self.metrics["CPU_max_core_percent"].append(max(usages))

    def _parse_freq(self, line: str) -> None:
        match = re.search(r"EMC_FREQ (\d+)%@?(\d+)?", line)
        if match:
            self.metrics["EMC_usage_percent"].append(int(match.group(1)))
            if match.group(2):
                self.metrics["EMC_freq_MHz"].append(int(match.group(2)))

        match = re.search(r"GR3D_FREQ (\d+)%@?(\d+)?", line)
        if match:
            self.metrics["GR3D_usage_percent"].append(int(match.group(1)))
            if match.group(2):
                self.metrics["GR3D_freq_MHz"].append(int(match.group(2)))

        match = re.search(r"VIC_FREQ (\d+)%@(\d+)", line)
        if match:
            self.metrics["VIC_usage_percent"].append(int(match.group(1)))
            self.metrics["VIC_freq_MHz"].append(int(match.group(2)))

    def _parse_temperatures(self, line: str) -> None:
        matches = re.findall(r"(\w+)@([\d\.]+)C", line)
        for name, value in matches:
            self.metrics[f"TEMP_{name}_C"].append(float(value))

    def _parse_power(self, line: str) -> None:
        matches = re.findall(r"(VDD_\w+)\s+(\d+)/(\d+)", line)
        for rail, current, avg in matches:
            self.metrics[f"{rail}_current_mW"].append(int(current))
            self.metrics[f"{rail}_avg_mW"].append(int(avg))

    # -------------------------
    # Stats
    # -------------------------

    def compute_stats(self) -> dict:
        results = {}

        for key, values in self.metrics.items():
            if not values:
                continue

            results[key] = {
                "min": min(values),
                "max": max(values),
                "avg": mean(values),
            }

        return results


# -------------------------
# CLI
# -------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute stats from tegrastats log file"
    )
    parser.add_argument(
        "logfile",
        type=Path,
        help="Path to tegrastats log file"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.logfile.exists():
        raise FileNotFoundError(f"File not found: {args.logfile}")

    parser = TegrastatsParser()

    with args.logfile.open("r", encoding="utf-8") as f:
        for line in f:
            parser.parse_line(line)

    stats = parser.compute_stats()

    if not stats:
        print("No metrics found.")
        return

    # Compute padding dynamically
    max_key_length = max(len(metric) for metric in stats.keys())

    for metric, values in sorted(stats.items()):
        padded_key = f"{metric}:".ljust(max_key_length + 2)

        print(
            f"{padded_key}\t"
            f"min={values['min']:.2f},\t"
            f"max={values['max']:.2f},\t"
            f"avg={values['avg']:.2f}"
        )

if __name__ == "__main__":
    main()
