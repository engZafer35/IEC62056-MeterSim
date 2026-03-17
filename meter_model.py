import re
import threading
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

LOAD_PROFILE_INTERVAL_MINUTES = 15


@dataclass
class LoadProfileEntry:
    """One load profile record: date, time, total energy, voltage, current, power factor."""
    timestamp: datetime
    total_energy_kwh: float   # cumulative total at this moment
    voltage_v: float
    current_a: float
    power_factor: float


@dataclass
class MeterState:
    serial_number: str = "12345678"  # 0.0.0
    total_import_kwh: float = 0.0  # 1.8.0
    total_export_kwh: float = 0.0  # 2.8.0
    instant_power_kw: float = 0.0  # 1.7.0
    voltage_v: float = 230.0  # 32.7.0
    # Son interval RAM’de tutulacak, eski tüm geçmiş diskten okunacak
    last_interval: LoadProfileEntry = None

    def snapshot_obis_readout(self) -> str:
        now = datetime.now()
        date_str = now.strftime("%y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

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
    Simülatör:
    - Ana load profile dosyası append-only
    - Snapshot dosyası otomatik oluşturulur (_total_endex.txt)
    - get_load_profile_between diskten okuyarak çalışır
    """

    def __init__(self, data_file: Path, interval_seconds: int = LOAD_PROFILE_INTERVAL_MINUTES * 60):
        self.state = MeterState()
        self.data_file = data_file
        # Snapshot dosyasını ana dosya isminden türet
        self.snapshot_file = data_file.with_name(f"{data_file.stem}_total_endex.txt")
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._load_snapshot()  # Açılışta snapshot yüklenir

    # ---------- public API ----------

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._save_snapshot()  # Kapanışta snapshot güncellenir

    def get_obis_readout(self) -> str:
        with self._lock:
            return self.state.snapshot_obis_readout()

    def get_load_profile_between(self, start: datetime, end: datetime) -> List[LoadProfileEntry]:
        """
        Diskten satır satır okuyarak aralıkta olan yük profillerini döndürür.
        RAM’de tüm geçmiş yüklenmez.
        """
        results = []
        try:
            with self.data_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("("):
                        continue
                    try:
                        entry = self._parse_profile_line(line)
                        if entry and start <= entry.timestamp <= end:
                            results.append(entry)
                    except ValueError:
                        continue
        except OSError:
            pass
        return results

    # ---------- internal ----------

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self._generate_interval()

    def _generate_interval(self) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        consumption = random.uniform(0.1, 0.6)
        duration_hours = LOAD_PROFILE_INTERVAL_MINUTES / 60.0
        avg_power_kw = consumption / duration_hours

        voltage = random.gauss(230.0, 5.0)
        voltage = max(210.0, min(240.0, voltage))
        power_factor = random.uniform(0.85, 1.0)
        # I = P / (V * PF), P in kW -> I in A: I = (P * 1000) / (V * PF)
        current_a = (avg_power_kw * 1000.0) / (voltage * power_factor) if (voltage * power_factor) > 0 else 0.0
        current_a = max(0.0, min(999.9, current_a))

        with self._lock:
            self.state.total_import_kwh += consumption
            self.state.instant_power_kw = max(0.0, random.gauss(avg_power_kw, avg_power_kw * 0.1))
            self.state.voltage_v = voltage

            entry = LoadProfileEntry(
                timestamp=now,
                total_energy_kwh=self.state.total_import_kwh,
                voltage_v=voltage,
                current_a=current_a,
                power_factor=power_factor,
            )
            self.state.last_interval = entry
            self._append_entry_to_file(entry)

    def _append_entry_to_file(self, entry: LoadProfileEntry) -> None:
        # Format: (YYYY-MM-DD)(HH:MM)(000000.000*kWh)(229*V)(000.0*A)(1.00)
        date_str = entry.timestamp.strftime("%Y-%m-%d")
        time_str = entry.timestamp.strftime("%H:%M")
        total_str = f"{entry.total_energy_kwh:011.3f}*kWh"
        voltage_str = f"{int(round(entry.voltage_v))}*V"
        current_str = f"{entry.current_a:05.1f}*A"
        pf_str = f"{entry.power_factor:.2f}"
        line = f"({date_str})({time_str})({total_str})({voltage_str})({current_str})({pf_str})\n"

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with self.data_file.open("a", encoding="utf-8") as f:
            f.write(line)
        self._save_snapshot()

    # ---------- snapshot methods ----------

    def _load_snapshot(self) -> None:
        """
        Snapshot dosyasını oku:
        - total_import_kwh ve son timestamp alınır
        - RAM’de sadece son interval tutulur
        """
        last_entry = None
        if self.data_file.exists():
            try:
                with self.data_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("("):
                            last_entry = self._parse_profile_line(line)
            except (OSError, ValueError):
                pass
        if last_entry is not None:
            self.state.total_import_kwh = last_entry.total_energy_kwh
            self.state.last_interval = last_entry
            return
        if not self.snapshot_file.exists():
            return
        try:
            with self.snapshot_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("total_import("):
                        val = line[len("total_import("):-1]
                        self.state.total_import_kwh = float(val)
                    elif line.startswith("last_timestamp("):
                        ts_str = line[len("last_timestamp("):-1]
                        ts = datetime.strptime(ts_str, "%y%m%d%H%M")
                        self.state.last_interval = LoadProfileEntry(
                            timestamp=ts, total_energy_kwh=self.state.total_import_kwh,
                            voltage_v=230.0, current_a=0.0, power_factor=1.0
                        )
        except OSError:
            return

    def _save_snapshot(self) -> None:
        """
        Snapshot dosyasına son timestamp ve toplam import yazılır
        """
        self.snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        last_ts = self.state.last_interval.timestamp if self.state.last_interval else datetime.now()
        with self.snapshot_file.open("w", encoding="utf-8") as f:
            f.write(f"last_timestamp({last_ts.strftime('%y%m%d%H%M')})\n")
            f.write(f"total_import({self.state.total_import_kwh:.2f})\n")

    @staticmethod
    def _parse_profile_line(line: str) -> Optional[LoadProfileEntry]:
        """
        Parse "(YYYY-MM-DD)(HH:MM)(total*kWh)(V*V)(I*A)(PF)" into LoadProfileEntry.
        """
        # Extract six (...) groups
        parts = re.findall(r"\(([^)]*)\)", line)
        if len(parts) < 6:
            raise ValueError("Malformed load profile line")
        date_str, time_str, total_str, voltage_str, current_str, pf_str = parts[:6]
        ts = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        total = float(total_str.replace("*kWh", ""))
        voltage = float(voltage_str.replace("*V", ""))
        current = float(current_str.replace("*A", ""))
        power_factor = float(pf_str)
        return LoadProfileEntry(
            timestamp=ts, total_energy_kwh=total,
            voltage_v=voltage, current_a=current, power_factor=power_factor
        )