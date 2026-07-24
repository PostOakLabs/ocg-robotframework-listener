"""Thin MCP JSON-RPC client for the AINumbers worker's `emit_chaingraph_artifact`
tool (Mode 1: `pre_computed_artifact`) -- the existing receipt path this
package reuses (BUILD-SPEC SS0/SS2). No worker code is added or forked; this
is a plain HTTP POST to the public /mcp endpoint using stdlib only (no new
runtime dependency for a listener that must stay lightweight and offline-safe).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ENDPOINT = "https://mcp.ainumbers.co/mcp"
_TIMEOUT_SECONDS = 10


class WorkerUnavailable(Exception):
    """Raised when the receipt endpoint cannot be reached or errors -- the
    listener catches this and degrades to offline-hash mode; it MUST NOT
    propagate up into the Robot Framework run (BUILD-SPEC SS2)."""


def request_receipt(artifact: dict[str, Any], endpoint: str = DEFAULT_ENDPOINT) -> dict[str, Any]:
    """POSTs an MCP `tools/call emit_chaingraph_artifact` request with
    `pre_computed_artifact` and returns the tool's `structuredContent`
    (the verified artifact + receipt fields)."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "emit_chaingraph_artifact",
            "arguments": {"pre_computed_artifact": artifact},
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WorkerUnavailable(str(exc)) from exc

    try:
        parsed = _parse_mcp_response(raw)
    except (ValueError, KeyError) as exc:
        raise WorkerUnavailable(f"malformed worker response: {exc}") from exc

    if "error" in parsed:
        raise WorkerUnavailable(f"worker error: {parsed['error']}")

    result = parsed.get("result", {})
    if result.get("isError"):
        raise WorkerUnavailable(f"emit_chaingraph_artifact reported an error: {result}")

    structured = result.get("structuredContent")
    if structured is None:
        raise WorkerUnavailable("worker response had no structuredContent")
    return structured


def _parse_mcp_response(raw: str) -> dict[str, Any]:
    """The worker may reply as a single JSON object or an SSE stream of
    `data: {...}` lines; handle both."""
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            candidate = line[len("data:"):].strip()
            if candidate:
                return json.loads(candidate)
    raise ValueError("no JSON payload found in response")
