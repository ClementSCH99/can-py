"""Immutable CAN capture manifest helpers.

The manifest describes closed CAN-owned sources only. NHR run association is a
separate post-test report and never mutates this file.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class CaptureManifestError(RuntimeError):
    """A CAN capture manifest is invalid or could not be persisted safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def portable_relative_path(path: Path, root: Path) -> str:
    """Return a canonical root-relative POSIX path or reject it."""
    root_resolved = root.resolve()
    candidate = path.resolve()
    try:
        relative = candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise CaptureManifestError(
            f"Capture source is outside the manifest directory: {path}"
        ) from exc
    value = relative.as_posix()
    validate_portable_path(value)
    return value


def validate_portable_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise CaptureManifestError("Manifest path must be a non-empty string")
    if "\\" in value:
        raise CaptureManifestError(f"Manifest path must use '/': {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.anchor or ":" in path.parts[0]:
        raise CaptureManifestError(f"Manifest path must be relative: {value!r}")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise CaptureManifestError(f"Manifest path is not canonical: {value!r}")
    if path.as_posix() != value:
        raise CaptureManifestError(f"Manifest path is not canonical: {value!r}")
    return value


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise CaptureManifestError(f"Could not write manifest/report {path}: {exc}") from exc


def build_capture_manifest(
    *,
    manifest_path: Path,
    capture_id: str,
    started_at_utc: str,
    ended_at_utc: str,
    final_state: str,
    closure_reason: str,
    frame_count: int,
    source_paths: Sequence[tuple[str, Path]],
    effective_config: Mapping[str, Any],
    profile: Mapping[str, Any] | None,
    dbc: Mapping[str, Any] | None,
    nhr_identity: Mapping[str, Any],
    forwarding_statistics: Mapping[str, Any] | None,
    merge_defaults: Mapping[str, Any],
) -> dict[str, Any]:
    if final_state not in {"completed", "failed"}:
        raise CaptureManifestError(f"Invalid capture final_state: {final_state!r}")
    root = manifest_path.parent
    sources = []
    for role, raw_path in source_paths:
        path = Path(raw_path)
        if not path.is_file():
            raise CaptureManifestError(f"Closed CAN source not found: {path}")
        sources.append(
            {
                "role": role,
                "path": portable_relative_path(path, root),
                "size_bytes": path.stat().st_size,
            }
        )
    payload = {
        "schema_version": 1,
        "capture_id": capture_id,
        "started_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "final_state": final_state,
        "closure_reason": closure_reason,
        "frame_count": frame_count,
        "sources": sources,
        "effective_config": dict(effective_config),
        "profile": dict(profile) if profile else None,
        "dbc": dict(dbc) if dbc else None,
        "nhr": dict(nhr_identity),
        "forwarding_statistics": (
            dict(forwarding_statistics) if forwarding_statistics is not None else None
        ),
        "merge_defaults": dict(merge_defaults),
    }
    def contains_run_id(node: Any) -> bool:
        if isinstance(node, Mapping):
            return any(key == "run_id" or contains_run_id(item) for key, item in node.items())
        if isinstance(node, list):
            return any(contains_run_id(item) for item in node)
        return False

    if contains_run_id(payload):
        raise CaptureManifestError("CAN capture manifest must not contain an NHR run_id")
    return payload


def load_capture_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureManifestError(f"Could not read CAN manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CaptureManifestError("Unsupported or invalid CAN manifest schema")
    if payload.get("final_state") != "completed":
        raise CaptureManifestError(
            f"CAN capture is not completed successfully: {payload.get('final_state')!r}"
        )
    capture_id = payload.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise CaptureManifestError("CAN manifest capture_id is invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise CaptureManifestError("CAN manifest sources must be a list")
    for source in sources:
        if not isinstance(source, dict):
            raise CaptureManifestError("CAN manifest source entry is invalid")
        relative = validate_portable_path(source.get("path"))
        resolved = (path.parent / PurePosixPath(relative)).resolve()
        try:
            resolved.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise CaptureManifestError("CAN manifest source escapes its directory") from exc
        if not resolved.is_file():
            raise CaptureManifestError(f"CAN manifest source not found: {relative}")
        size = source.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise CaptureManifestError("CAN manifest source size_bytes is invalid")
        if resolved.stat().st_size != size:
            raise CaptureManifestError(f"CAN manifest source size changed: {relative}")
    return payload


def source_path_for_role(
    manifest_path: Path, payload: Mapping[str, Any], role: str
) -> Path:
    candidates = [item for item in payload["sources"] if item.get("role") == role]
    if len(candidates) != 1:
        raise CaptureManifestError(
            f"Expected exactly one CAN source with role {role!r}, found {len(candidates)}"
        )
    relative = validate_portable_path(candidates[0]["path"])
    return (manifest_path.parent / PurePosixPath(relative)).resolve()
