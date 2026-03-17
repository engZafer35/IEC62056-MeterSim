import socket
import argparse
import time
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="IEC62056 TCP meter client")

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server IP address (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Server port (default: 5000)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Query interval in seconds (default: 10)",
    )

    parser.add_argument(
        "--start",
        default="2603171000",
        help="Load profile start timestamp (YYMMDDhhmm, default: 2603171000)",
    )

    parser.add_argument(
        "--end",
        default=None,
        help="Load profile end timestamp (YYMMDDhhmm, default: now)",
    )

    return parser.parse_args()


def query_meter(host, port, start, end):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))

            # 1. Identification
            s.sendall(b"/?!\r\n")
            print("ID Response:")
            print(s.recv(1024).decode())

            # 2. ACK
            s.sendall(b"ACK050\r\n")
            print("ACK Response:")
            print(s.recv(1024).decode())

            # 3. Load profile
            request = f"P.01({start})({end})\r\n".encode()
            s.sendall(request)

            print("Load Profile Response:")
            print(s.recv(4096).decode())

    except Exception as e:
        print(f"Connection error: {e}")


def main():
    args = parse_args()

    # Eğer end belirtilmemişse şu anki zaman
    if args.end is None:
        args.end = datetime.now().strftime("%y%m%d%H%M")

    print("Starting TCP client...")
    print(f"Target: {args.host}:{args.port}")
    print(f"Interval: {args.interval} sec")
    print(f"Load profile start: {args.start} (end = current time on each query)")

    try:
        while True:
            print("\n--- New Query ---")
            end = datetime.now().strftime("%y%m%d%H%M")
            query_meter(args.host, args.port, args.start, end)
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nStopping client...")


if __name__ == "__main__":
    main()