"""JCS-aligned canonicalizer + execution hash — Python transliteration.

Provenance: `chaingraph/kernels/_hash.mjs` in PostOakLabs/ainumbers
(`cgCanon` / `executionHash`, OCG Standard SS2/SS6), as of commit referenced in
this package's README. This module MUST stay byte-for-byte parity with that
canonical JS implementation — verified by `tests/test_canon.py` against fixed
fixture vectors computed with the real `_hash.mjs`. Do not "improve" the
canonicalization here without re-deriving fixtures from the JS source; a
second, drifting canon is exactly what the OCG single-lineage rule forbids.

Canonicalization: recursively sort object keys by Unicode code point,
preserve array order, emit minimal-whitespace JSON (no spaces, non-ASCII
left as literal UTF-8 rather than \\uXXXX-escaped, matching JS
`JSON.stringify`), SHA-256 over the UTF-8 bytes, lowercase hex digest.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

_MAX_SAFE_INTEGER = 2**53 - 1


def assert_ijson(value: Any) -> None:
    """Mirrors `_hash.mjs` assertIJson: reject values that cannot round-trip
    through I-JSON (RFC 7493) and therefore cannot canonicalize stably."""
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite number ({value}) is not valid I-JSON; cannot canonicalize for hashing (RFC 8785 SS3.2.2.3).")
        return
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValueError(f"Integer {value} exceeds 2^53 and is not safe I-JSON; pass it as a string (RFC 7493).")
        return
    if isinstance(value, list):
        for item in value:
            assert_ijson(item)
        return
    if isinstance(value, dict):
        for key in value:
            assert_ijson(value[key])
        return


def cg_canon(value: Any) -> Any:
    """Recursively sort dict keys by Unicode code point; preserve array order."""
    if isinstance(value, list):
        return [cg_canon(item) for item in value]
    if isinstance(value, dict):
        return {key: cg_canon(value[key]) for key in sorted(value.keys())}
    return value


def _dumps(value: Any) -> str:
    # separators=(",", ":") matches JS JSON.stringify's no-whitespace output.
    # ensure_ascii=False matches JS leaving non-ASCII as literal UTF-8 chars.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def canonical_preimage(policy_parameters: dict, output_payload: dict) -> str:
    """The exact string that gets hashed. Exposed for debugging / parity proofs."""
    obj = {"policy_parameters": policy_parameters, "output_payload": output_payload}
    assert_ijson(obj)
    return _dumps(cg_canon(obj))


def execution_hash(policy_parameters: dict, output_payload: dict) -> str:
    """Bare lowercase hex SHA-256 (matches worker.mjs / browser tools). No 'sha256:' prefix."""
    preimage = canonical_preimage(policy_parameters, output_payload)
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()
