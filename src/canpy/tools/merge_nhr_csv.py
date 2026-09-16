"""Merge a closed CAN capture with one exact finalized NHR workflow run."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Optional, Sequence

from canpy.capture_manifest import (
    CaptureManifestError,
    load_capture_manifest,
    sha256_file,
    source_path_for_role,
    utc_now_text,
    write_json_atomic,
)
from canpy.nhr import NHRRecordingEvidenceError, read_nhr_workflow_evidence
from canpy.writers import MergedCSVError, MergedCSVWriter, load_signal_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge one closed CAN capture with one exact finalized NHR-RT run."
    )
    daily = parser.add_argument_group("daily options")
    expert = parser.add_argument_group("expert overrides")
    legacy = parser.add_argument_group("detailed compatibility mode")
    daily.add_argument("--can-manifest", default=None)
    daily.add_argument("--nhr-run-id", required=True)
    expert.add_argument("--nhr-scope", choices=("session", "sequence", "stage"))
    expert.add_argument("--nhr-stage-index", type=int)
    expert.add_argument("--signals", default=None)
    expert.add_argument("--signals-file", default=None)
    expert.add_argument("--can-stale-after", type=float, default=None)
    expert.add_argument("--output", default=None)
    expert.add_argument("--nhr-finalize-timeout", type=float, default=60.0)
    expert.add_argument("--nhr-poll-interval", type=float, default=0.5)
    legacy.add_argument("--can-csv", default=None)
    legacy.add_argument("--nhr-url", default=None)
    legacy.add_argument("--nhr-instrument", default=None)
    return parser


def _default_output(can_csv: Path) -> Path:
    name = (
        can_csv.name.replace("can_capture_", "merged_capture_", 1)
        if can_csv.name.startswith("can_capture_")
        else f"merged_{can_csv.name}"
    )
    return can_csv.with_name(name)


def _resolve_invocation(args) -> dict[str, Any]:
    manifest_path = Path(args.can_manifest).resolve() if args.can_manifest else None
    detailed_values = (args.can_csv, args.nhr_url, args.nhr_instrument)
    overrides: list[str] = []
    manifest_sha256 = None
    if manifest_path:
        if any(value is not None for value in detailed_values):
            raise MergedCSVError(
                "--can-manifest cannot be mixed with --can-csv, --nhr-url, or "
                "--nhr-instrument"
            )
        manifest = load_capture_manifest(manifest_path)
        can_csv = source_path_for_role(manifest_path, manifest, "csv")
        nhr = manifest.get("nhr")
        defaults = manifest.get("merge_defaults")
        if not isinstance(nhr, dict) or not isinstance(defaults, dict):
            raise CaptureManifestError("CAN manifest lacks NHR identity or merge defaults")
        nhr_url = nhr.get("service_url")
        instrument = nhr.get("instrument_id")
        default_signals = defaults.get("signals")
        default_scope = defaults.get("scope")
        default_stale = defaults.get("can_stale_after_s")
        capture_id = manifest["capture_id"]
        manifest_sha256 = sha256_file(manifest_path)
    else:
        if not all(detailed_values):
            raise MergedCSVError(
                "Use --can-manifest with --nhr-run-id, or provide --can-csv, "
                "--nhr-url, and --nhr-instrument"
            )
        can_csv = Path(args.can_csv).resolve()
        nhr_url = args.nhr_url
        instrument = args.nhr_instrument
        default_signals = []
        default_scope = "session"
        default_stale = 2.5
        capture_id = can_csv.stem

    if not isinstance(nhr_url, str) or not nhr_url.strip():
        raise MergedCSVError("NHR service URL is missing")
    if not isinstance(instrument, str) or not instrument.strip():
        raise MergedCSVError("NHR instrument identity is missing")
    if default_scope not in {"session", "sequence", "stage"}:
        raise MergedCSVError("Manifest merge scope is invalid")
    if (
        isinstance(default_stale, bool)
        or not isinstance(default_stale, (int, float))
        or default_stale <= 0
    ):
        raise MergedCSVError("Manifest CAN stale threshold is invalid")
    if not isinstance(default_signals, list):
        raise MergedCSVError("Manifest merge signals are invalid")
    if any(
        not isinstance(signal, str)
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", signal) is None
        for signal in default_signals
    ) or len(default_signals) != len(set(default_signals)):
        raise MergedCSVError("Manifest merge signals are invalid or duplicated")

    signals = set(default_signals)
    if args.signals is not None:
        signals = {item.strip() for item in args.signals.split(",") if item.strip()}
        overrides.append("--signals")
    if args.signals_file:
        signals.update(load_signal_file(args.signals_file))
        overrides.append("--signals-file")
    if not signals:
        raise MergedCSVError("At least one CAN signal must be selected")

    scope = args.nhr_scope or default_scope
    stale = args.can_stale_after if args.can_stale_after is not None else default_stale
    output = Path(args.output).resolve() if args.output else _default_output(can_csv)
    if args.nhr_scope is not None:
        overrides.append("--nhr-scope")
    if args.nhr_stage_index is not None:
        overrides.append("--nhr-stage-index")
    if args.can_stale_after is not None:
        overrides.append("--can-stale-after")
    if args.output is not None:
        overrides.append("--output")
    if stale <= 0:
        raise MergedCSVError("--can-stale-after must be positive")
    if scope == "stage" and (
        args.nhr_stage_index is None or args.nhr_stage_index < 0
    ):
        raise MergedCSVError("--nhr-stage-index is required and non-negative for stage")
    if scope != "stage" and args.nhr_stage_index is not None:
        raise MergedCSVError("--nhr-stage-index is valid only with --nhr-scope stage")
    return {
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "capture_id": capture_id,
        "can_csv": str(can_csv),
        "nhr_url": nhr_url,
        "nhr_instrument": instrument,
        "nhr_scope": scope,
        "nhr_stage_index": args.nhr_stage_index,
        "output": str(output),
        "signals": sorted(signals),
        "can_stale_after": float(stale),
        "overrides": overrides,
    }


def run_merge(
    *,
    can_csv: str,
    nhr_url: str,
    nhr_instrument: str,
    nhr_run_id: str,
    nhr_scope: str,
    nhr_stage_index: Optional[int],
    output: str,
    signals: Sequence[str],
    can_stale_after: float = 2.5,
    nhr_finalize_timeout: float = 60.0,
    nhr_poll_interval: float = 0.5,
):
    evidence = read_nhr_workflow_evidence(
        nhr_url,
        nhr_instrument,
        nhr_run_id,
        scope=nhr_scope,
        stage_index=nhr_stage_index,
        timeout_s=nhr_finalize_timeout,
        poll_interval_s=nhr_poll_interval,
    )
    result = MergedCSVWriter(stale_after_s=can_stale_after).merge(
        can_csv_path=can_csv,
        nhr_csv_path=evidence.csv_path,
        output_path=output,
        signals=signals,
    )
    return evidence, result


def _write_report(invocation, evidence, result) -> Path:
    merged_path = Path(result.path).resolve()
    report_path = merged_path.with_suffix(".report.json")
    payload = {
        "schema_version": 1,
        "can_manifest": (
            {"path": str(invocation["manifest_path"]), "sha256": invocation["manifest_sha256"]}
            if invocation["manifest_path"] else None
        ),
        "capture_id": invocation["capture_id"],
        "nhr_run_id": evidence.run_id,
        "nhr_instrument": invocation["nhr_instrument"],
        "workflow_terminal_state": evidence.workflow_state,
        "scope": invocation["nhr_scope"],
        "stage_index": invocation["nhr_stage_index"],
        "nhr_artifact": {
            "path": evidence.csv_path,
            "role": evidence.role,
            "size_bytes": evidence.size_bytes,
            "sha256": evidence.sha256,
            "manifest_path": getattr(evidence, "manifest_path", None),
        },
        "merged_csv": str(merged_path),
        "signals": invocation["signals"],
        "can_start_utc": result.can_start_utc,
        "can_end_utc": result.can_end_utc,
        "nhr_start_utc": result.nhr_start_utc,
        "nhr_end_utc": result.nhr_end_utc,
        "overlap_duration_s": result.overlap_duration_s,
        "can_rows_before_nhr": result.can_rows_before_nhr,
        "can_rows_after_nhr": result.can_rows_after_nhr,
        "nhr_rows_merged": result.nhr_rows_merged,
        "can_stale_after_s": invocation["can_stale_after"],
        "created_at_utc": utc_now_text(),
    }
    write_json_atomic(report_path, payload)
    return report_path


def print_merge_report(evidence, result, report_path=None, overrides=()) -> None:
    print(f"[OK] Merged CSV saved: {result.path}")
    if report_path:
        print(f"[OK] Merge report saved: {report_path}")
    print(f"  NHR run: {evidence.run_id} ({evidence.workflow_state})")
    print(f"  NHR artifact: {evidence.role} ({evidence.csv_path})")
    print(f"  CAN UTC: {result.can_start_utc} -> {result.can_end_utc}")
    print(f"  NHR UTC: {result.nhr_start_utc} -> {result.nhr_end_utc}")
    print(f"  Overlap: {result.overlap_duration_s:.6f} s")
    print(f"  CAN rows before NHR: {result.can_rows_before_nhr}")
    print(f"  CAN rows after NHR: {result.can_rows_after_nhr}")
    print(f"  NHR rows merged: {result.nhr_rows_merged}")
    print(f"  Explicit overrides: {', '.join(overrides) if overrides else 'none'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        invocation = _resolve_invocation(args)
        evidence, result = run_merge(
            can_csv=invocation["can_csv"],
            nhr_url=invocation["nhr_url"],
            nhr_instrument=invocation["nhr_instrument"],
            nhr_run_id=args.nhr_run_id,
            nhr_scope=invocation["nhr_scope"],
            nhr_stage_index=invocation["nhr_stage_index"],
            output=invocation["output"],
            signals=invocation["signals"],
            can_stale_after=invocation["can_stale_after"],
            nhr_finalize_timeout=args.nhr_finalize_timeout,
            nhr_poll_interval=args.nhr_poll_interval,
        )
        report_path = _write_report(invocation, evidence, result) if Path(result.path).is_file() else None
    except (CaptureManifestError, MergedCSVError, NHRRecordingEvidenceError, OSError) as exc:
        print(f"[ERROR] Merge products were not completed; source evidence was preserved: {exc}")
        return 1
    print_merge_report(evidence, result, report_path, invocation["overrides"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
