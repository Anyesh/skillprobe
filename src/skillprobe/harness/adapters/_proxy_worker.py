import argparse
import logging
from pathlib import Path

from aiohttp import web

from skillprobe.config import ProxyConfig
from skillprobe.proxy.handler import create_app
from skillprobe.storage.database import Database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db", type=str, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    db = Database(Path(args.db))
    db.initialize()

    config = ProxyConfig(
        host="127.0.0.1",
        port=args.port,
        db_path=Path(args.db),
    )
    app = create_app(config, db)

    try:
        web.run_app(app, host="127.0.0.1", port=args.port, print=None)
    finally:
        db.close()


if __name__ == "__main__":
    main()
