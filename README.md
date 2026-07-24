# ocg-robotframework-listener

OCG Robot Framework listener -- emits [OpenChainGraph](https://ainumbers.co/chaingraph/standard/) receipts from Robot Framework runs (RF Listener API v3).

At the end of a Robot Framework run this listener hashes a normalized descriptor
of the result (test/suite outcomes, not raw file bytes) and posts it to the
public AINumbers MCP worker's `emit_chaingraph_artifact` tool, which returns a
signed, verifiable OCG receipt bound to that run. If the worker is unreachable
the listener degrades to a local, offline hash file -- it never fails or alters
the underlying RF run.

**Is not:** a fork or rewrite of Robot Framework, and it adds no RF-specific
code to the AINumbers worker beyond reusing its existing receipt tool.

## Install

```bash
pip install ocg-rf-listener
```

## Usage

```bash
robot --listener ocg_rf_listener.OcgReceiptListener tests/
```

Offline / air-gapped mode (never calls the network):

```bash
robot --listener "ocg_rf_listener.OcgReceiptListener:offline=True" tests/
```

After the run, next to your output file (`output.xml` by default):

- **online:** `output.ocg-receipt.json` -- the signed OCG receipt.
- **offline (or worker unreachable):** `output.ocg-hash.json` -- the normalized
  descriptor + `execution_hash`, so a receipt can be minted later from the
  exact same bytes.

`execution_hash` is also written to the RF console/syslog output on every run
(see "Known limitation" below re: `log.html`).

## What gets hashed

Raw result-file bytes are **not** hashed directly -- attribute-order and
whitespace noise in `output.xml` would break reproducibility across
environments/RF versions. Instead a normalized `rf_execution_log@1` descriptor
is built (suite name/status/timing, pass/fail/skip totals, per-test
name/status/elapsed) plus a `result_file_sha256` chain-of-custody link to the
exact bytes on disk, and that descriptor is JCS-canonicalized (RFC 8785) and
SHA-256 hashed -- the same canonicalization the AINumbers worker and browser
tools use (`chaingraph/kernels/_hash.mjs` lineage; see `src/ocg_rf_listener/canon.py`
header for provenance). `tests/test_canon.py` fixture-tests this Python port
byte-for-byte against real output from that canonical JS module.

## RF format support

Supports current RF (7.x) `output.xml` and, on RF >= 7.2, `result.json`.
`--legacyoutput` (pre-7.0 shape) is detected and recorded in the descriptor's
`rf_output_format` field rather than silently mis-parsed.

## Fold-in notes from build-time research (2026-07-24)

Before building, this package's authors re-checked the current RF Listener API
against the original build spec and found two things worth recording:

1. **The listener hook is `output_file(path)`, not `result_file(path)`.**
   `result_file(self, kind, path)` exists only on RF's internal `LoggerApi`
   (used by RF's own console/file loggers) -- it is not part of the public
   `robot.api.interfaces.ListenerV3` surface a `--listener` plugin can
   implement. `output_file(path)` is the public, always-fired hook for a
   written output file (xml or json, per `--output`), and is what this
   package uses.
2. **Known limitation: `execution_hash` is not injected into `log.html`.**
   `output_file` fires *after* `output.xml` has already been fully written,
   and `log.html`/`report.html` are generated from that already-serialized
   file. A message logged from `output_file` therefore has no test/keyword
   context left to attach to and does not appear in the generated report --
   confirmed by running a real `robot` CLI invocation and diffing the output.
   Reaching into `log.html`/`report.html` post-generation to splice in a
   message would be fragile, non-standard, and easy to break on RF's own
   template updates, so this package deliberately does not do it. The
   `execution_hash` is authoritative in the sidecar receipt/hash file and in
   the RF console/syslog output; treat the receipt file, not `log.html`, as
   the record of truth. A version that logs during `end_suite` (before
   serialization) could get a message into the report, but at that point the
   result file has not been written yet and `result_file_sha256` -- the
   descriptor's chain-of-custody link to the actual bytes on disk -- would not
   be available; this is a real ordering conflict, not an oversight, and is
   left as a follow-up if surfacing inside `log.html` specifically becomes a
   requirement.
3. Current RF release line at build time: 7.4.x (7.4.2 is the latest bugfix
   release; 7.4 added secret-variable support). Secret variables do not
   change anything here -- descriptor fields are structural (names/statuses/
   timings), never keyword arguments or variable values, so a secret marked
   `!secret` in a suite is never at risk of ending up in a receipt.

## Rebot-compatible export (deferred, Tim gate)

RF's suite/test/keyword hierarchy is a field-proven shape for a possible OCG
**execution-log export profile** (SPEC.md SS13) -- rendering an OCG chain run in
RF's own `log.html`/`report.html` via `rebot`. That is the *reverse* direction
from this package (OCG chain -> RF-compatible output, not RF -> OCG receipt)
and is out of scope here. It would touch `SPEC.md` and the AINumbers worker and
is explicitly deferred to a separate export-profile work unit if ever pursued.

## Development

```bash
pip install -e ".[test]"
pytest
```

`tests/test_canon.py` checks the Python canonicalizer against fixtures
generated from the real `chaingraph/kernels/_hash.mjs` -- if it goes red, the
Python port has drifted from the canonical JS lineage; fix the port, not the
fixtures. `tests/test_listener.py` runs a real Robot Framework suite through
the listener end-to-end (offline mode, and a mocked worker-failure path) and
confirms the receipt/hash file recomputes independently to the same
`execution_hash`.

## License

Apache-2.0 (see `LICENSE`), matching Robot Framework's own license.
