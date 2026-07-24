"""End-to-end: run a tiny suite with the listener attached in offline mode,
then verify the written `.ocg-hash.json` recomputes to the same execution_hash
independently (BUILD-SPEC SS6 done-criterion #2/#3)."""

import json
from pathlib import Path

from robot.api import ExecutionResult, TestSuite

import ocg_rf_listener.listener as listener_mod
from ocg_rf_listener.canon import execution_hash
from ocg_rf_listener.client import WorkerUnavailable
from ocg_rf_listener.descriptor import build_descriptor


def _run_suite(tmp_path: Path, offline: bool) -> Path:
    suite = TestSuite("Ocg Demo Suite")
    suite.resource.imports.library("BuiltIn")
    t1 = suite.tests.create("Passes")
    t1.body.create_keyword("Log", args=["hello"])
    t2 = suite.tests.create("Also passes")
    t2.body.create_keyword("Log", args=["world"])

    outdir = tmp_path / "out"
    outdir.mkdir()
    listener = f"ocg_rf_listener.OcgReceiptListener:offline={offline}"
    suite.run(outputdir=str(outdir), listener=[listener], output="output.xml", log=None, report=None)
    return outdir / "output.xml"


def test_offline_mode_writes_hash_descriptor_and_it_is_reproducible(tmp_path):
    output_xml = _run_suite(tmp_path, offline=True)
    assert output_xml.exists()

    hash_path = output_xml.with_suffix("").with_suffix(".ocg-hash.json")
    assert hash_path.exists(), "listener must write <name>.ocg-hash.json in offline mode"

    with open(hash_path, "r", encoding="utf-8") as f:
        written = json.load(f)

    assert written["ocg_kind"] == "rf_execution_log_hash@1"
    assert written["output_payload"]["ocg_kind"] == "rf_execution_log@1"
    assert written["output_payload"]["totals"]["passed"] == 2
    assert written["output_payload"]["totals"]["failed"] == 0
    assert len(written["output_payload"]["tests"]) == 2

    # Recompute independently from the same result file and confirm parity --
    # the whole point of the descriptor approach (BUILD-SPEC SS3).
    result = ExecutionResult(str(output_xml))
    descriptor = build_descriptor(result, str(output_xml), "xml")
    recomputed = execution_hash(written["policy_parameters"], descriptor)
    assert recomputed == written["execution_hash"]


def test_listener_never_raises_when_worker_unreachable(tmp_path, monkeypatch):
    # Force the network path to fail -- tests must never make a real call to
    # the production worker. The listener MUST degrade to the offline hash
    # file, never raise out of a listener hook (BUILD-SPEC SS2/SS6.4).
    def _boom(artifact, endpoint=None):
        raise WorkerUnavailable("simulated network failure")

    monkeypatch.setattr(listener_mod, "request_receipt", _boom)

    output_xml = _run_suite(tmp_path, offline=False)
    assert output_xml.exists()
    base = output_xml.with_suffix("")
    hash_path = Path(f"{base}.ocg-hash.json")
    receipt_path = Path(f"{base}.ocg-receipt.json")
    assert hash_path.exists(), "worker failure must degrade to offline hash file"
    assert not receipt_path.exists()
