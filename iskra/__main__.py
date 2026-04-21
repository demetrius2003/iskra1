"""CLI: python -m iskra [--config PATH]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from iskra.core.config import load_config
from iskra.core.main_loop import MainLoop


def main() -> None:
    parser = argparse.ArgumentParser(description="Iskra-1 — autonomous thought loop for LLMs")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=config.logging.format)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    loop = MainLoop(config)
    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        logging.getLogger("iskra").info("Прервано пользователем (Ctrl+C).")
        loop._cleanup()
    except SystemExit:
        raise
    except Exception as e:
        logging.getLogger("iskra").exception("Fatal: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
