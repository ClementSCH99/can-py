from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from urllib.request import urlopen

import pytest

from canpy.nhr import (
    BMS_POC_V2_MAPPING,
    ExternalSnapshot,
    ExternalSnapshotAssembler,
    ExternalSnapshotForwarder,
)
from canpy.storage import CANFrame


nhr9300 = pytest.importorskip("nhr9300")


def _can_frame(timestamp_utc, can_id, signals):
    return CANFrame(
        timestamp_utc=timestamp_utc,
        source_timestamp=timestamp_utc.timestamp(),
        can_id=can_id,
        dlc=8,
        data=b"\x00" * 8,
        is_extended=False,
        is_remote=False,
        is_error=False,
        parsed_signals=signals,
    )


def _wait_for_source_health(client, instrument_id, expected, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = client.interlocks(instrument_id)
        sources = status["external_sources"]["sources"]
        if sources and sources[0]["health"] == expected:
            return sources[0]
        time.sleep(0.05)
    raise AssertionError(f"source health did not become {expected!r}")


def test_forwarder_publishes_through_current_nhr_rt_simulator(tmp_path):
    from nhr9300 import NHRServiceClient
    from nhr9300.service import build_server

    server, manager = build_server(
        {
            "output_dir": str(tmp_path),
            "instruments": [
                {"id": "sim-forwarder", "backend": "simulator"}
            ],
        },
        port=0,
        announce=False,
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    forwarder = ExternalSnapshotForwarder(
        "sim-forwarder",
        "bms-poc-v2",
        base_url=base_url,
        reconnect_delays_s=(0.0,),
    ).start()
    try:
        forwarder.wait_ready()
        source_timestamp = datetime.now(timezone.utc)
        forwarder.offer(
            ExternalSnapshot(
                timestamp_utc=source_timestamp,
                health="ok",
                signals={"pack_voltage_v": 90.0, "hv_permissive": True},
            )
        )

        deadline = time.monotonic() + 2.0
        while forwarder.statistics().sent_count < 1:
            if time.monotonic() >= deadline:
                raise AssertionError("snapshot was not published before timeout")
            time.sleep(0.01)

        status = NHRServiceClient(base_url).interlocks("sim-forwarder")
        source = status["external_sources"]["sources"][0]
        assert source["source_id"] == "bms-poc-v2"
        assert source["sequence"] == 0
        assert source["timestamp_utc"] == source_timestamp.isoformat()
        assert source["health"] == "ok"
    finally:
        forwarder.stop()
        server.shutdown()
        server_thread.join(timeout=2)
        manager.close()
        server.server_close()


def test_poc_mapping_loss_debounce_recovery_and_monitor_runtime(tmp_path):
    from nhr9300 import NHRServiceClient
    from nhr9300.monitor import build_monitor
    from nhr9300.service import build_server

    server, manager = build_server(
        {
            "output_dir": str(tmp_path),
            "instruments": [
                {"id": "sim-poc-v2", "backend": "simulator", "rate_hz": 5}
            ],
        },
        port=0,
        announce=False,
    )
    service_thread = threading.Thread(target=server.serve_forever, daemon=True)
    service_thread.start()
    service_host, service_port = server.server_address
    base_url = f"http://{service_host}:{service_port}"
    client = NHRServiceClient(base_url)

    monitor = build_monitor(client, "sim-poc-v2", port=0)
    monitor_thread = threading.Thread(
        target=monitor.serve_forever, daemon=True
    )
    monitor_thread.start()
    monitor_host, monitor_port = monitor.server_address

    assembler = ExternalSnapshotAssembler(BMS_POC_V2_MAPPING)
    forwarder = ExternalSnapshotForwarder(
        "sim-poc-v2",
        "bms-poc-v2",
        base_url=base_url,
        publish_rate_hz=5.0,
        signal_max_age_s=2.5,
        communication_loss_fault_after_s=5.0,
        reconnect_delays_s=(0.0,),
    ).start()
    try:
        forwarder.wait_ready()
        initial_time = datetime.now(timezone.utc)
        assert assembler.observe(
            _can_frame(
                initial_time,
                0x431,
                {"minCellV": 3.25, "maxCellV": 4.10},
            )
        ) is None
        complete = assembler.observe(
            _can_frame(
                initial_time,
                0x441,
                {"minCellTemp": 18.5, "maxCellTemp": 41.0},
            )
        )
        forwarder.offer(complete)

        healthy = _wait_for_source_health(client, "sim-poc-v2", "ok", 2.0)
        assert healthy["source_id"] == "bms-poc-v2"
        assert healthy["last_rejection"] is None

        with urlopen(
            f"http://{monitor_host}:{monitor_port}/api/runtime", timeout=2
        ) as response:
            runtime = json.load(response)
        assert runtime["external_sources"]["sources"][0]["health"] == "ok"

        _wait_for_source_health(client, "sim-poc-v2", "stale", 4.0)
        faulted = _wait_for_source_health(
            client, "sim-poc-v2", "fault", 4.0
        )
        assert faulted["age_s"] >= 5.0

        recovered_time = datetime.now(timezone.utc)
        forwarder.offer(
            assembler.observe(
                _can_frame(
                    recovered_time,
                    0x431,
                    {"minCellV": 3.24, "maxCellV": 4.11},
                )
            )
        )
        forwarder.offer(
            assembler.observe(
                _can_frame(
                    datetime.now(timezone.utc),
                    0x441,
                    {"minCellTemp": 19.0, "maxCellTemp": 40.5},
                )
            )
        )
        recovered = _wait_for_source_health(
            client, "sim-poc-v2", "ok", 2.0
        )
        assert recovered["sequence"] > faulted["sequence"]
        assert recovered["last_rejection"] is None
    finally:
        forwarder.stop()
        monitor.shutdown()
        monitor_thread.join(timeout=2)
        monitor.server_close()
        server.shutdown()
        service_thread.join(timeout=2)
        manager.close()
        server.server_close()
