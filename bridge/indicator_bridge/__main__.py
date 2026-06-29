import asyncio
import logging

from .app import Bridge
from .config import load_config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config()
    try:
        asyncio.run(Bridge(cfg).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
