import argparse
import signal
import sys
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
        help="Dinlenecek IP adresi (varsayılan: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Dinlenecek TCP portu (varsayılan: 5000)",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=Path("meter_data.txt"),
        help="Yük profili verilerini yazacağı dosya (varsayılan: meter_data.txt)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=15 * 60,
        help="Yük profili kayıt periyodu (saniye). Test için düşürebilirsiniz. "
        "Gerçekte 15 dk = 900 sn.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    meter = MeterSimulator(
        data_file=args.data_file,
        interval_seconds=args.interval_seconds,
    )
    meter.start()

    server = MeterTCPServer(args.host, args.port, meter)
    server.start()

    print(
        f"TCP sayaç simülatörü {args.host}:{args.port} üzerinde çalışıyor. "
        f"Yük profili dosyası: {args.data_file}"
    )
    print(
        "Bağlantı akışı:\n"
        "1) /?!\\r\\n gönder → sayaç kimliği gelir\n"
        "2) ACK050\\r\\n gönder → sayaç short readout paketini gönderir\n"
        "3) P.01(YYMMDDhhmm)(YYMMDDhhmm)\\r\\n → yük profili cevabı"
    )

    def handle_sig(sig, frame):
        print("\nKapatılıyor...")
        server.stop()
        meter.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    # Basit sonsuz döngü; sinyal gelene kadar bekle
    signal.pause()


if __name__ == "__main__":
    main()

