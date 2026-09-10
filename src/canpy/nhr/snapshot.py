"""Assemble complete NHR-RT snapshots from decoded CAN frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from canpy.storage import CANFrame

from .forwarder import ExternalSnapshot, SignalValue


@dataclass(frozen=True)
class SignalMapping:
    """Map one DBC signal to its public NHR external-source name and unit."""

    dbc_name: str
    snapshot_name: str
    unit: str

    def __post_init__(self) -> None:
        if not self.dbc_name.strip() or not self.snapshot_name.strip():
            raise ValueError("DBC and snapshot signal names must not be empty")
        if not self.unit.strip():
            raise ValueError("signal unit must not be empty")


BMS_POC_V2_MAPPING = (
    SignalMapping("minCellTemp", "MinCellTemp", "degC"),
    SignalMapping("maxCellTemp", "MaxCellTemp", "degC"),
    SignalMapping("minCellV", "MinCellVolt", "V"),
    SignalMapping("maxCellV", "MaxCellVolt", "V"),
)


class ExternalSnapshotAssembler:
    """Keep the newest mapped values and emit complete conservative snapshots.

    Each cached signal retains the UTC timestamp of the CAN frame that supplied
    it. A complete snapshot uses the oldest contributing timestamp, so repeated
    5 Hz publication never makes a slower CAN value appear newer than it is.
    """

    def __init__(self, mappings: Iterable[SignalMapping]) -> None:
        normalized = tuple(mappings)
        if not normalized:
            raise ValueError("at least one signal mapping is required")
        dbc_names = [item.dbc_name for item in normalized]
        snapshot_names = [item.snapshot_name for item in normalized]
        if len(set(dbc_names)) != len(dbc_names):
            raise ValueError("DBC signal mappings must be unique")
        if len(set(snapshot_names)) != len(snapshot_names):
            raise ValueError("snapshot signal mappings must be unique")

        self.mappings: Tuple[SignalMapping, ...] = normalized
        self._by_dbc = {item.dbc_name: item for item in normalized}
        self._values: Dict[str, Tuple[SignalValue, Any]] = {}

    @property
    def required_dbc_signals(self) -> frozenset:
        return frozenset(self._by_dbc)

    def observe(self, frame: CANFrame) -> Optional[ExternalSnapshot]:
        """Update mapped values and return a complete snapshot when possible."""
        decoded = frame.parsed_signals
        if not isinstance(decoded, Mapping):
            return None

        updated = False
        for dbc_name, mapping in self._by_dbc.items():
            if dbc_name not in decoded:
                continue
            self._values[mapping.snapshot_name] = (
                decoded[dbc_name],
                frame.timestamp_utc,
            )
            updated = True

        if not updated or len(self._values) != len(self.mappings):
            return None

        timestamp_utc = min(timestamp for _, timestamp in self._values.values())
        signals = {name: value for name, (value, _) in self._values.items()}
        return ExternalSnapshot(
            timestamp_utc=timestamp_utc,
            health="ok",
            signals=signals,
        )
