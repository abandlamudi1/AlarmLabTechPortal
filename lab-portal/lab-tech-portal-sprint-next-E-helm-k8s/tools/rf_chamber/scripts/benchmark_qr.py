"""Benchmark QR code generation throughput for RF chamber links.

Usage:
    python tools/rf_chamber/scripts/benchmark_qr.py --runs 200 --barcode CH-0001
"""
from __future__ import annotations

import argparse
import statistics
import time

from flask import Flask

from tools.rf_chamber.rf_chamber_app import _build_chamber_link, _qr_code_data


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure QR code generation performance")
    parser.add_argument(
        "--runs",
        type=int,
        default=200,
        help="Number of QR codes to generate for the measurement",
    )
    parser.add_argument(
        "--barcode",
        default="CH-0001",
        help="Sample barcode to embed in the QR code link",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    barcode = args.barcode.upper()

    app = Flask("rf-benchmark")

    with app.app_context():
        # Warm up Flask url generation path once to remove initialization cost.
        url = _build_chamber_link(barcode)
        _qr_code_data(url)

        timings = []
        for _ in range(args.runs):
            start = time.perf_counter()
            _qr_code_data(url)
            timings.append(time.perf_counter() - start)

    total = sum(timings)
    avg = statistics.mean(timings)
    sorted_timings = sorted(timings)
    index = max(0, int(round(0.95 * len(sorted_timings) - 1)))
    p95 = sorted_timings[index]

    print(f"Runs: {args.runs}")
    print(f"Total time: {total:.4f}s")
    print(f"Average per QR: {avg * 1000:.2f} ms")
    print(f"95th percentile: {p95 * 1000:.2f} ms")


if __name__ == "__main__":
    main()
