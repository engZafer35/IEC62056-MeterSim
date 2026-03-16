import threading
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple


LOAD_PROFILE_INTERVAL_MINUTES = 15


@dataclass
class LoadProfileEntry:
    timestamp: datetime
    consumption_kwh: float


@dataclass
class MeterState:
    serial_number: str = "12345678"  # 0.0.0
    total_import_kwh: float = 0.0  # 1.8.0
    total_export_kwh: float = 0.0  # 2.8.0
    instant_power_kw: float = 0.0  # 1.7.0
    voltage_v: float = 230.0  # 32.7.0
    load_profile: List[LoadProfileEntry] = field(default_factory=list)

    def snapshot_obis_readout(self) -> str:
        """Create a short/default OBIS readout string."""
        now = datetime.now()
        date_str = now.strftime("%y-%m-%d")  # 0.9.2
        time_str = now.strftime("%H:%M:%S")  # 0.9.1

        lines = [
            f"0.0.0({self.serial_number})",
            f"1.8.0({self.total_import_kwh:010.2f}*kWh)",
            f"2.8.0({self.total_export_kwh:010.2f}*kWh)",
            f"1.7.0({self.instant_power_kw:07.2f}*kW)",
            f"32.7.0({self.voltage_v:05.1f}*V)",
            f"0.9.1({time_str})",
            f"0.9.2({date_str})",
            "!",
        ]
        return "\r\n".join(lines)


class MeterSimulator:
    """
    Manages simulated meter state and periodic load profile generation.
    Persists load profile to a simple text file.
    """

    def __init__(
        self,
        data_file: Path,
        interval_seconds: int = LOAD_PROFILE_INTERVAL_MINUTES * 60,
    ) -> None:
        self.state = MeterState()
        self.data_file = data_file
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._load_existing_profile()

    # ---------- public API ----------

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def get_obis_readout(self) -> str:
        with self._lock:
            return self.state.snapshot_obis_readout()

    def get_load_profile_between(
        self, start: datetime, end: datetime
    ) -> List[LoadProfileEntry]:
        with self._lock:
            return [e for e in self.state.load_profile if start <= e.timestamp <= end]

    # ---------- internal ----------

    def _run_loop(self) -> None:
        """Background loop to periodically append new load profile entries."""
        while not self._stop_event.wait(self.interval_seconds):
            self._generate_interval()

    def _generate_interval(self) -> None:
        """
        Generate one 15-minute interval:
        - random positive consumption
        - update total import
        - derive instant power and voltage around nominal values
        - append to file
        """
        now = datetime.now().replace(second=0, microsecond=0)

        # Simulated consumption in kWh for this interval (e.g. 0.1–0.6 kWh per 15 min)
        consumption = random.uniform(0.1, 0.6)

        # Approximate average power for the interval
        duration_hours = LOAD_PROFILE_INTERVAL_MINUTES / 60.0
        avg_power_kw = consumption / duration_hours

        # Small random variation for instantaneous power and voltage
        instant_power = max(0.0, random.gauss(avg_power_kw, avg_power_kw * 0.1))
        voltage = random.gauss(230.0, 2.0)

        entry = LoadProfileEntry(timestamp=now, consumption_kwh=consumption)

        with self._lock:
            self.state.load_profile.append(entry)
            self.state.total_import_kwh += consumption
            self.state.instant_power_kw = instant_power
            self.state.voltage_v = voltage
            self._append_entry_to_file(entry)

    def _load_existing_profile(self) -> None:
        """
        Load existing load profile data from file, if it exists.
        Rebuilds total_import_kwh from the file to keep things consistent.
        """
        if not self.data_file.exists():
            return

        entries: List[LoadProfileEntry] = []
        total_import = 0.0
        try:
            with self.data_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("P.01("):
                        continue
                    try:
                        ts, cons = self._parse_profile_line(line)
                        entry = LoadProfileEntry(timestamp=ts, consumption_kwh=cons)
                        entries.append(entry)
                        total_import += cons
                    except ValueError:
                        # Skip malformed lines
                        continue
        except OSError:
            return

        with self._lock:
            self.state.load_profile = entries
            self.state.total_import_kwh = total_import

    def _append_entry_to_file(self, entry: LoadProfileEntry) -> None:
        """
        Append a line using the format:
        P.01(YYMMDDhhmm)(0000.42)
        """
        ts_str = entry.timestamp.strftime("%y%m%d%H%M")
        cons_str = f"{entry.consumption_kwh:07.2f}"
        line = f"P.01({ts_str})({cons_str})\n"

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with self.data_file.open("a", encoding="utf-8") as f:
            f.write(line)

    @staticmethod
    def _parse_profile_line(line: str) -> Tuple[datetime, float]:
        """
        Parse "P.01(YYMMDDhhmm)(vvvv.vv)" into (datetime, float).
        """
        # Very simple parser assuming format is valid
        first_open = line.find("(")
        first_close = line.find(")", first_open + 1)
        second_open = line.find("(", first_close + 1)
        second_close = line.find(")", second_open + 1)

        if min(first_open, first_close, second_open, second_close) == -1:
            raise ValueError("Malformed load profile line")

        ts_str = line[first_open + 1 : first_close]
        cons_str = line[second_open + 1 : second_close]

        ts = datetime.strptime(ts_str, "%y%m%d%H%M")
        consumption = float(cons_str)
        return ts, consumption

