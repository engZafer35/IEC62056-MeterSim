import threading
import random
from dataclasses import dataclass, field
from datetime import datetime
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
                    if not line.startswith("P.01("):
                        continue
                    try:
                        ts, cons = self._parse_profile_line(line)
                        if start <= ts <= end:
                            results.append(LoadProfileEntry(ts, cons))
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

        instant_power = max(0.0, random.gauss(avg_power_kw, avg_power_kw * 0.1))
        voltage = random.gauss(230.0, 2.0)

        entry = LoadProfileEntry(timestamp=now, consumption_kwh=consumption)

        with self._lock:
            self.state.last_interval = entry
            self.state.total_import_kwh += consumption
            self.state.instant_power_kw = instant_power
            self.state.voltage_v = voltage
            self._append_entry_to_file(entry)

    def _append_entry_to_file(self, entry: LoadProfileEntry) -> None:
        ts_str = entry.timestamp.strftime("%y%m%d%H%M")
        cons_str = f"{entry.consumption_kwh:07.2f}"
        line = f"P.01({ts_str})({cons_str})\n"

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with self.data_file.open("a", encoding="utf-8") as f:
            f.write(line)

    # ---------- snapshot methods ----------

    def _load_snapshot(self) -> None:
        """
        Snapshot dosyasını oku:
        - total_import_kwh ve son timestamp alınır
        - RAM’de sadece son interval tutulur
        """
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
                        self.state.last_interval = LoadProfileEntry(timestamp=ts, consumption_kwh=0.0)
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
    def _parse_profile_line(line: str) -> Tuple[datetime, float]:
        """
        Parse "P.01(YYMMDDhhmm)(vvvv.vv)" into (datetime, float)
        """
        first_open = line.find("(")
        first_close = line.find(")", first_open + 1)
        second_open = line.find("(", first_close + 1)
        second_close = line.find(")", second_open + 1)
        if min(first_open, first_close, second_open, second_close) == -1:
            raise ValueError("Malformed load profile line")

        ts_str = line[first_open + 1:first_close]
        cons_str = line[second_open + 1:second_close]

        ts = datetime.strptime(ts_str, "%y%m%d%H%M")
        consumption = float(cons_str)
        return ts, consumption