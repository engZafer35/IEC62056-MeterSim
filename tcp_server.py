import socket
import threading
from queue import Queue
from typing import Tuple

from meter_model import MeterSimulator
from iec62056_protocol import ConnectionState, CRLF, ProtocolConfig


class MeterTCPServer:
    """
    Single-threaded worker queue for handling TCP connections sequentially.
    Accepts connections immediately and queues them for processing in order.
    """

    def __init__(self, host: str, port: int, meter: MeterSimulator, meter_id: str) -> None:
        self.host = host
        self.port = port
        self.meter = meter
        self.meter_id = meter_id
        self._sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._conn_queue: Queue[Tuple[socket.socket, Tuple[str, int]]] = Queue()

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(100)  # backlog size

        # Accept loop thread
        threading.Thread(target=self._accept_loop, daemon=True).start()
        # Worker thread for sequentially processing clients
        threading.Thread(target=self._worker_loop, daemon=True).start()

        print(f"MeterTCPServer started on {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        print("MeterTCPServer stopped")

    # ---------- internal ----------

    def _accept_loop(self) -> None:
        """Accepts incoming connections and puts them into a queue."""
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._sock.accept()
                print(f"\033[91mClient connected: IP {addr[0]}, PORT {addr[1]}, FD {client_sock.fileno()}\033[0m")
                self._conn_queue.put((client_sock, addr))
            except OSError:
                break

    def _worker_loop(self) -> None:
        """Sequentially handles queued client connections."""
        while not self._stop_event.is_set():
            client_sock, addr = self._conn_queue.get()
            if client_sock is None:
                self._conn_queue.task_done()
                continue
            try:
                self._handle_client(client_sock, addr)
            finally:
                self._conn_queue.task_done()

    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        """Existing client handler logic."""
        config = ProtocolConfig(meter_id=f"/{self.meter_id}")
        conn_state = ConnectionState(self.meter, config=config)
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
                            data_bytes = response.encode("ascii")
                            chunk_size = 1024
                            for i in range(0, len(data_bytes), chunk_size):
                                client_sock.send(data_bytes[i : i + chunk_size])
                                # small delay is optional; remove if not needed
                        except OSError:
                            return
