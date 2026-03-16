import socket
import threading
from typing import Tuple

from meter_model import MeterSimulator
from iec62056_protocol import ConnectionState, CRLF


class MeterTCPServer:
    """
    Very simple single-thread-per-connection TCP server.
    The meter opens the listening socket; external clients connect to it.
    """

    def __init__(self, host: str, port: int, meter: MeterSimulator) -> None:
        self.host = host
        self.port = port
        self.meter = meter
        self._sock: socket.socket | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow quick restart
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(5)

        accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        accept_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    # ---------- internal ----------

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._sock.accept()
            except OSError:
                break
            t = threading.Thread(
                target=self._handle_client, args=(client_sock, addr), daemon=True
            )
            t.start()

    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        conn_state = ConnectionState(self.meter)
        with client_sock:
            buf = ""
            while not self._stop_event.is_set():
                try:
                    data = client_sock.recv(1024)
                except OSError:
                    break
                if not data:
                    break
                buf += data.decode("ascii", errors="ignore")

                # IEC62056-21 over serial uses CR LF; here we treat CRLF or LF as terminator.
                while CRLF in buf or "\n" in buf:
                    if CRLF in buf:
                        line, sep, rest = buf.partition(CRLF)
                    else:
                        line, sep, rest = buf.partition("\n")
                    buf = rest
                    response = conn_state.handle_line(line)
                    if response:
                        try:
                            client_sock.sendall(response.encode("ascii"))
                        except OSError:
                            return

