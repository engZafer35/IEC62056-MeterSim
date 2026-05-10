import argparse
import signal
import sys
import time
from pathlib import Path

from meter_model import MeterSimulator
from tcp_server import MeterTCPServer


def parse_args():
    parser = argparse.ArgumentParser(
        description="IEC 62056 TCP elektrik sayacı simülatörü"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Dinlenecek IP adresi (varsayılan: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Dinlenecek TCP portu (varsayılan: 5000)",
    )
    parser.add_argument(
        "--meter-id",
        default="ZD5ME666-1003",
        help="Sayaç kimliği / model numarası (varsayılan: ZD5ME666-1003)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=15 * 60,
        help="Yük profili kayıt periyodu (saniye). Test için düşürebilirsiniz. "
        "Gerçekte 15 dk = 900 sn.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("."),
        help="Sayaç kayıt dizini: yük profili ve snapshot hem buradan okunur hem buraya yazılır "
        "(varsayılan: ./)",
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
        f"TCP sayaç simülatörü {args.host}:{args.port} üzerinde çalışıyor.\n"
        f"Kayıt dizini (okuma/yazma): {meter.storage_dir}\n"
        f"Yük profili dosyası: {data_file}"
    )
    print(
        "Bağlantı akışı:\n"
        "1) /?!\\r\\n gönder → sayaç kimliği gelir\n"
        "2) ACK050\\r\\n gönder → sayaç short readout paketini gönderir\n"
        "3) P.01(YYMMDDhhmm)(YYMMDDhhmm)\\r\\n → yük profili cevabı"
    )

    def shutdown():
        print("\nKapatılıyor...")
        server.stop()
        meter.stop()
        print("Temiz kapandı.")
        sys.exit(0)

    def handle_sig(sig, frame):
        shutdown()

    # Signal handler (Windows'ta SIGTERM her zaman çalışmayabilir ama zararı yok)
    signal.signal(signal.SIGINT, handle_sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_sig)

    # 🔥 Windows uyumlu bekleme
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()