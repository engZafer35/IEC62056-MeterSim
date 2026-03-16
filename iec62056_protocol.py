from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from meter_model import MeterSimulator, LoadProfileEntry


CR = "\r"
LF = "\n"
CRLF = CR + LF


@dataclass
class ProtocolConfig:
    meter_id: str = "/ZD5ME666-1003"


class ConnectionState:
    """
    Simple IEC 62056-21 state machine per TCP connection.
    """

    def __init__(self, meter: MeterSimulator, config: Optional[ProtocolConfig] = None):
        self.meter = meter
        self.config = config or ProtocolConfig()
        self.handshake_done = False
        self.baudrate_ack_received = False

    def handle_line(self, line: str) -> Optional[str]:
        """
        Handle a single received line (without CRLF).
        Returns a response string (potentially multi-line, including final CRLF),
        or None if no response is needed.
        """
        line = line.strip()
        if not line:
            return None

        # 1) Initial handshake: /?!
        if line.startswith("/?!"):
            self.handshake_done = True
            # Respond with meter ID
            return self.config.meter_id + CRLF

        # 2) ACK0x0 (baudrate change) – for TCP we just accept and ignore baud
        if line.upper().startswith("ACK") and self.handshake_done:
            self.baudrate_ack_received = True
            # Immediately send short/default readout as many meters do
            readout = self.meter.get_obis_readout()
            return readout + CRLF

        # 3) Load profile request: P.01(YYMMDDhhmm)(YYMMDDhhmm)
        if line.upper().startswith("P.01("):
            return self._handle_load_profile_request(line)

        # Other messages (e.g. baudrate change commands, unsupported OBIS queries)
        # are simply ignored or could be extended later.
        return None

    # ---------- helpers ----------

    def _handle_load_profile_request(self, line: str) -> Optional[str]:
        """
        Parse P.01(YYMMDDhhmm)(YYMMDDhhmm) and build response with entries:
        P.01(YYMMDDhhmm)(vvvv.vv)
        ...
        !
        """
        try:
            start_str, end_str = self._parse_two_params(line)
            start_dt = datetime.strptime(start_str, "%y%m%d%H%M")
            end_dt = datetime.strptime(end_str, "%y%m%d%H%M")
        except ValueError:
            # Malformed request
            return None

        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        entries: List[LoadProfileEntry] = self.meter.get_load_profile_between(
            start=start_dt, end=end_dt
        )

        lines: List[str] = []
        for e in entries:
            ts_str = e.timestamp.strftime("%y%m%d%H%M")
            cons_str = f"{e.consumption_kwh:07.2f}"
            lines.append(f"P.01({ts_str})({cons_str})")
        lines.append("!")

        return CRLF.join(lines) + CRLF

    @staticmethod
    def _parse_two_params(line: str) -> tuple[str, str]:
        """
        Extract the two (...) groups from a command like:
        P.01(2401010000)(2401070000)
        """
        first_open = line.find("(")
        first_close = line.find(")", first_open + 1)
        second_open = line.find("(", first_close + 1)
        second_close = line.find(")", second_open + 1)

        if min(first_open, first_close, second_open, second_close) == -1:
            raise ValueError("Malformed command")

        p1 = line[first_open + 1 : first_close]
        p2 = line[second_open + 1 : second_close]
        return p1, p2

