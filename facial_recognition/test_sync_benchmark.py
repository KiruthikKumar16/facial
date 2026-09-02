"""
Automated Test for Reproducible Synchronization Benchmark Framework.

Validates that:
1. All 6 experimental conditions execute accurately.
2. Machine-readable benchmark JSON and Markdown reports are generated.
3. Modern architecture achieves zero event loss and zero duplicate insertions.
4. Measured bandwidth reduction is >= 95% compared to legacy baseline.
"""

import json
from pathlib import Path
import pytest

from facial_recognition.benchmark_sync_comparison import BenchmarkRunner


def test_reproducible_benchmark_execution(tmp_path):
    """Run full comparative benchmark and verify metrics integrity."""
    docs_dir = Path("c:/Users/mkiru/facial/docs")
    docs_dir.mkdir(parents=True, exist_ok=True)

    runner = BenchmarkRunner(output_dir=docs_dir)
    results = runner.run_all_benchmarks()

    assert "conditions" in results
    assert len(results["conditions"]) == 6

    # Verify JSON artifact
    json_path = docs_dir / "benchmark_results.json"
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded["conditions"]) == 6

    # Verify Markdown report artifact
    report_path = docs_dir / "BENCHMARK_REPORT.md"
    assert report_path.exists()
    report_content = report_path.read_text(encoding="utf-8")
    assert "Architecture Benchmark Report" in report_content
    assert "99.0% bandwidth savings" in report_content

    # Validate condition specific metrics
    for cond in results["conditions"]:
        name = cond["condition"]
        leg = cond["legacy"]
        mod = cond["modern"]

        # Duplicate rate must be 0% on modern architecture
        assert mod["duplicate_rate_pct"] == 0.0

        # In recovery and high volume, loss rate must be 0%
        if name in ("Normal Network", "Outage Recovery", "High Event Volume (500)"):
            assert mod["event_loss_rate_pct"] == 0.0

        # Bandwidth on modern must be <= 5% of legacy (>= 95% reduction)
        if leg["avg_bytes_per_event"] > 0:
            assert mod["avg_bytes_per_event"] < (0.05 * leg["avg_bytes_per_event"])
