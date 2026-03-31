import logging

from aiohttp import web

from skillprobe.config import ProxyConfig
from skillprobe.proxy.handler import create_app
from skillprobe.storage.database import Database


def run_proxy(config: ProxyConfig):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    db = Database(config.db_path)
    db.initialize()
    app = create_app(config, db)
    print(f"Skillprobe proxy listening on http://{config.host}:{config.port}")
    print(f"Forwarding Anthropic -> {config.anthropic_api_url}")
    print(f"Forwarding OpenAI   -> {config.openai_api_url}")
    print(f"Database: {config.db_path}")
    print()
    print("Connect your tools:")
    print(f"  ANTHROPIC_BASE_URL=http://{config.host}:{config.port} claude <prompt>")
    print(f"  OPENAI_BASE_URL=http://{config.host}:{config.port} <tool>")
    print()
    try:
        web.run_app(app, host=config.host, port=config.port, print=None)
    finally:
        db.close()
