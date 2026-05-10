import argparse
import signal
import sys
import time
from pathlib import Path

from meter_model import MeterSimulator
from tcp_server import MeterTCPServer


def parse_args():
    parser = argparse.ArgumentParser(
        description="IEC 62056 TCP electricity meter simulator"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="TCP port to listen on (default: 5000)",
    )
    parser.add_argument(
        "--meter-id",
        default="ZD5ME666-1003",
        help="Meter ID / model string (default: ZD5ME666-1003)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=15 * 60,
        help="Load profile append interval in seconds (default 900 = 15 min; lower for testing)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("."),
        help="Data directory: load profile and snapshot files are read/written here (default: ./)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    storage_dir = args.output.expanduser().resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)

    meter = MeterSimulator(
        storage_dir=storage_dir,
        meter_id=args.meter_id,
        interval_seconds=args.interval_seconds,
    )
    data_file = meter.data_file
    meter.start()

    server = MeterTCPServer(args.host, args.port, meter, meter_id=args.meter_id)
    server.start()

    print(
        f"TCP meter simulator listening on {args.host}:{args.port}\n"
        f"Data directory (read/write): {meter.storage_dir}\n"
        f"Load profile file: {data_file}"
    )
    print(
        "Protocol flow:\n"
        "1) Send /?!\\r\\n -> identification response\n"
        "2) Send ACK050\\r\\n -> short/default OBIS readout\n"
        "3) P.01(YYMMDDhhmm)(YYMMDDhhmm)\\r\\n -> load profile response"
    )

    def shutdown():
        print("\nShutting down...")
        server.stop()
        meter.stop()
        print("Stopped cleanly.")
        sys.exit(0)

    def handle_sig(sig, frame):
        shutdown()

    # SIGTERM may not work on all Windows setups; harmless if ignored.
    signal.signal(signal.SIGINT, handle_sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_sig)

    # Sleep loop (works on Windows without signal.pause)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()