import re
from collections import defaultdict
from statistics import mean


class TegrastatsParser:
    def __init__(self):
        self.metrics = defaultdict(list)

    def parse_line(self, line: str) -> None:
        """Parse a single tegrastats line."""
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
            used = int(match.group(1))
            total = int(match.group(2))
            self.metrics["RAM_used_MB"].append(used)
            self.metrics["RAM_total_MB"].append(total)

    def _parse_swap(self, line: str) -> None:
        match = re.search(r"SWAP (\d+)/(\d+)MB", line)
        if match:
            used = int(match.group(1))
            total = int(match.group(2))
            self.metrics["SWAP_used_MB"].append(used)
            self.metrics["SWAP_total_MB"].append(total)

    def _parse_cpu(self, line: str) -> None:
        match = re.search(r"CPU \[(.*?)\]", line)
        if match:
            cores = match.group(1).split(",")
            usages = []

            for core in cores:
                usage_match = re.search(r"(\d+)%@", core)
                if usage_match:
                    usages.append(int(usage_match.group(1)))

            if usages:
                self.metrics["CPU_avg_percent"].append(mean(usages))
                self.metrics["CPU_max_core_percent"].append(max(usages))

    def _parse_freq(self, line: str) -> None:
        # EMC
        match = re.search(r"EMC_FREQ (\d+)%@?(\d+)?", line)
        if match:
            self.metrics["EMC_usage_percent"].append(int(match.group(1)))
            if match.group(2):
                self.metrics["EMC_freq_MHz"].append(int(match.group(2)))

        # GR3D
        match = re.search(r"GR3D_FREQ (\d+)%@?(\d+)?", line)
        if match:
            self.metrics["GR3D_usage_percent"].append(int(match.group(1)))
            if match.group(2):
                self.metrics["GR3D_freq_MHz"].append(int(match.group(2)))

        # VIC
        match = re.search(r"VIC_FREQ (\d+)%@(\d+)", line)
        if match:
            self.metrics["VIC_usage_percent"].append(int(match.group(1)))
            self.metrics["VIC_freq_MHz"].append(int(match.group(2)))

    def _parse_temperatures(self, line: str) -> None:
        matches = re.findall(r"(\w+)@([\d\.]+)C", line)
        for name, value in matches:
            key = f"TEMP_{name}_C"
            self.metrics[key].append(float(value))

    def _parse_power(self, line: str) -> None:
        # Example: VDD_IN 7867/7656
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
# Usage example
# -------------------------

def main():
    parser = TegrastatsParser()

    # Read from file or stdin
    # Example: cat log.txt | python script.py
    import sys

    for line in sys.stdin:
        parser.parse_line(line)

    stats = parser.compute_stats()

    for metric, values in sorted(stats.items()):
        print(f"{metric}: min={values['min']:.2f}, max={values['max']:.2f}, avg={values['avg']:.2f}")


if __name__ == "__main__":
    main()
