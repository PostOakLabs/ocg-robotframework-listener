"""Build the normalized `rf_execution_log@1` descriptor (BUILD-SPEC SS3).

Raw result-file bytes are not hashed directly -- whitespace/attribute-order
noise in output.xml/result.json breaks reproducibility across environments.
Instead a normalized descriptor is built from the parsed result and THAT is
what gets JCS-canonicalized and hashed (see canon.py). `result_file_sha256`
still preserves a tamper-evident link to the exact bytes on disk.
"""

from __future__ import annotations

import hashlib
from typing import Any


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _test_entries(suite) -> list:
    entries = []
    for test in suite.all_tests:
        entries.append({
            "name": test.name,
            "status": str(test.status),
            "elapsed": round(test.elapsed_time.total_seconds(), 3) if test.elapsed_time is not None else 0.0,
        })
    return entries


def build_descriptor(result, result_file_path: str, rf_output_format: str) -> dict[str, Any]:
    """`result` is a `robot.result.ExecutionResult`'s `.suite` (or the
    ExecutionResult itself, both expose `.suite`/`.statistics`)."""
    suite = result.suite if hasattr(result, "suite") else result
    stats = result.statistics.total if hasattr(result, "statistics") else suite.statistics.total

    descriptor = {
        "ocg_kind": "rf_execution_log@1",
        "rf_output_format": rf_output_format,
        "result_file_sha256": sha256_file(result_file_path),
        "suite": {
            "name": suite.name,
            "status": str(suite.status),
            "starttime": _isoformat(getattr(suite, "start_time", None)),
            "endtime": _isoformat(getattr(suite, "end_time", None)),
            "elapsed": round(suite.elapsed_time.total_seconds(), 3) if getattr(suite, "elapsed_time", None) is not None else 0.0,
        },
        "totals": {
            "passed": stats.passed,
            "failed": stats.failed,
            "skipped": stats.skipped,
        },
        "tests": _test_entries(suite),
    }
    return descriptor


def _isoformat(value) -> str:
    if value is None:
        return ""
    # robot.model timestamps are already-normalized datetimes on RF >= 7.0.
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
