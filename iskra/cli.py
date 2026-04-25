"""CLI entry: ``python -m iskra`` or console script ``iskra``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import yaml
from pydantic import ValidationError

from iskra.core.config import load_config
from iskra.core.main_loop import MainLoop
from iskra.core.preflight import PreflightError


def main() -> None:
    parser = argparse.ArgumentParser(description="Iskra-1 — autonomous thought loop for LLMs")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"YAML parse error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as e:
        print(f"Invalid configuration: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=config.logging.format)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    loop = MainLoop(config)
    try:
        asyncio.run(loop.run())
    except PreflightError as e:
        print(f"Предстартовая проверка не пройдена: {e}", file=sys.stderr)
        sys.exit(1)
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
