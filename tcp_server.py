import selectors
import socket
import threading
from dataclasses import dataclass
from typing import Optional, Tuple

from meter_model import MeterSimulator
from iec62056_protocol import ConnectionState, CRLF, ProtocolConfig

# Selector key.data for the listening socket (not a ClientSession)
_LISTEN = object()


@dataclass
class ClientSession:
    sock: socket.socket
    addr: Tuple[str, int]
    conn_state: ConnectionState
    recv_buf: str = ""


class MeterTCPServer:
    """
    Single-threaded I/O multiplexing: one background thread runs a select() loop
    on the listen socket and all client sockets. No per-connection threads.
    """

    def __init__(self, host: str, port: int, meter: MeterSimulator, meter_id: str) -> None:
        self.host = host
        self.port = port
        self.meter = meter
        self.meter_id = meter_id
        self._sock: Optional[socket.socket] = None
        self._stop_event = threading.Event()
        self._io_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(100)

        self._io_thread = threading.Thread(target=self._select_loop, daemon=True)
        self._io_thread.start()

        print(f"MeterTCPServer started on {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._io_thread is not None and self._io_thread.is_alive():
            self._io_thread.join(timeout=10.0)
        self._io_thread = None
        print("MeterTCPServer stopped")

    # ---------- internal ----------

    def _select_loop(self) -> None:
        listen = self._sock
        if listen is None:
            return

        sel = selectors.DefaultSelector()
        try:
            sel.register(listen, selectors.EVENT_READ, _LISTEN)
        except OSError:
            return

        try:
            while not self._stop_event.is_set():
                try:
                    events = sel.select(timeout=0.25)
                except OSError:
                    break
                for key, _mask in events:
                    if key.data is _LISTEN:
                        self._accept_new_clients(sel, key.fileobj)
                    elif isinstance(key.data, ClientSession):
                        self._process_client_read(sel, key.data)
        finally:
            for key in list(sel.get_map().values()):
                try:
                    sel.unregister(key.fileobj)
                except OSError:
                    pass
                try:
                    key.fileobj.close()
                except OSError:
                    pass
            try:
                sel.close()
            except OSError:
                pass
            self._sock = None

    def _accept_new_clients(self, sel: selectors.BaseSelector, listen_sock: socket.socket) -> None:
        while True:
            try:
                conn, addr = listen_sock.accept()
            except OSError:
                break
            print(
                f"\033[91mClient connected: IP {addr[0]}, PORT {addr[1]}, "
                f"FD {conn.fileno()}\033[0m"
            )
            cfg = ProtocolConfig(meter_id=f"/{self.meter_id}")
            session = ClientSession(
                sock=conn,
                addr=addr,
                conn_state=ConnectionState(self.meter, config=cfg),
            )
            try:
                sel.register(conn, selectors.EVENT_READ, session)
            except OSError:
                try:
                    conn.close()
                except OSError:
                    pass
                break

    def _process_client_read(self, sel: selectors.BaseSelector, session: ClientSession) -> None:
        sock = session.sock
        try:
            chunk = sock.recv(8192)
        except OSError:
            self._remove_client(sel, session)
            return
        if not chunk:
            self._remove_client(sel, session)
            return

        session.recv_buf += chunk.decode("ascii", errors="ignore")

        while CRLF in session.recv_buf or "\n" in session.recv_buf:
            if CRLF in session.recv_buf:
                line, _sep, session.recv_buf = session.recv_buf.partition(CRLF)
            else:
                line, _sep, session.recv_buf = session.recv_buf.partition("\n")
            response = session.conn_state.handle_line(line)
            if not response:
                continue
            try:
                data_bytes = response.encode("ascii")
                sock.sendall(data_bytes)
            except OSError:
                self._remove_client(sel, session)
                return

    def _remove_client(self, sel: selectors.BaseSelector, session: ClientSession) -> None:
        try:
            sel.unregister(session.sock)
        except OSError:
            pass
        try:
            session.sock.close()
        except OSError:
            pass
