"""Robot Framework Listener API v3 -> OCG receipt (BUILD-SPEC SS2).

Usage:
    robot --listener ocg_rf_listener.OcgReceiptListener tests/
    robot --listener "ocg_rf_listener.OcgReceiptListener:offline=True" tests/

A listener MUST NOT alter test outcomes. Every network / parse failure here
degrades to writing a local `.ocg-hash.json` and logging a warning -- it
never raises out of a listener hook.

NOTE (folded in at build time, 2026-07-24, per the RF-RECEIPT-1 web-search
gate): the public Listener API v3 interface (`robot.api.interfaces.ListenerV3`,
RF 7.4.2 installed) has no `result_file(path)` hook -- that name only exists
on the internal `LoggerApi` (`result_file(self, kind, path)`, used by RF's own
console/file loggers) and is not reachable from a `--listener` plugin. The
public, always-fired hook for a written output file (xml or json, depending
on `--output`) is `output_file(path)`. BUILD-SPEC SS2 named `result_file` --
this implementation uses `output_file` instead; the behavior described in
SS2 (hash the written result file, mint or degrade a receipt) is unchanged.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

from robot.api import ExecutionResult, logger

from .canon import execution_hash
from .client import DEFAULT_ENDPOINT, WorkerUnavailable, request_receipt
from .descriptor import build_descriptor

ROBOT_LISTENER_API_VERSION = 3

_LEGACY_XML_MARKER = "generator=\"legacyoutput\""


class OcgReceiptListener:
    """Register with `--listener ocg_rf_listener.OcgReceiptListener`."""

    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, offline: bool = False, endpoint: str = DEFAULT_ENDPOINT):
        # RF passes CLI listener args as strings; accept "True"/"False" too.
        self.offline = str(offline).lower() in ("1", "true", "yes")
        self.endpoint = endpoint

    def output_file(self, path) -> None:
        if not path:
            return  # output file creation disabled (`--output NONE`)
        path = str(path)
        try:
            self._handle_result_file(path)
        except Exception as exc:  # noqa: BLE001 -- a listener must never fail the run
            logger.warn(f"ocg_rf_listener: could not process result file {path}: {exc}")

    def _handle_result_file(self, path: str) -> None:
        rf_output_format = self._detect_format(path)
        result = ExecutionResult(path)
        descriptor = build_descriptor(result, path, rf_output_format)
        policy_parameters: dict[str, Any] = {}
        exec_hash = execution_hash(policy_parameters, descriptor)

        base, _ext = os.path.splitext(path)

        if self.offline:
            self._write_offline_hash(base, policy_parameters, descriptor, exec_hash)
            return

        artifact = {
            "mandate_type": "rf_execution_log",
            "tool_id": "rf-execution-log",
            "tool_version": "1",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "execution_hash": exec_hash,
            "chain": [],
            "policy_parameters": policy_parameters,
            "output_payload": descriptor,
        }

        try:
            receipt = request_receipt(artifact, endpoint=self.endpoint)
        except WorkerUnavailable as exc:
            logger.warn(f"ocg_rf_listener: worker unreachable ({exc}); degrading to offline hash")
            self._write_offline_hash(base, policy_parameters, descriptor, exec_hash)
            return

        receipt_path = f"{base}.ocg-receipt.json"
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)
        logger.info(f"OCG execution_hash: {exec_hash}")
        logger.info(f"OCG receipt written: {receipt_path}")

    def _write_offline_hash(self, base: str, policy_parameters: dict, descriptor: dict, exec_hash: str) -> None:
        hash_path = f"{base}.ocg-hash.json"
        payload = {
            "ocg_kind": "rf_execution_log_hash@1",
            "policy_parameters": policy_parameters,
            "output_payload": descriptor,
            "execution_hash": exec_hash,
            "note": "Computed offline (worker unreachable or --ocg-offline). Mint a receipt later from these exact bytes.",
        }
        with open(hash_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"OCG execution_hash (offline): {exec_hash}")
        logger.info(f"OCG offline hash descriptor written: {hash_path}")

    @staticmethod
    def _detect_format(path: str) -> str:
        if path.endswith(".json"):
            return "json"
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
        except OSError:
            return "xml"
        return "legacy-xml" if _LEGACY_XML_MARKER in head else "xml"
