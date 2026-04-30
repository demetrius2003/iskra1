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

    parent = argparse.ArgumentParser(add_help=False)

    parent.add_argument(

        "--config",

        default="config.yaml",

        help="Path to config.yaml (default: ./config.yaml)",

    )



    parser = argparse.ArgumentParser(

        description="Iskra-1 - autonomous thought loop for LLMs",

        parents=[parent],

    )

    sub = parser.add_subparsers(dest="command", required=False)



    sub.add_parser("run", parents=[parent], help="Запуск основного цикла (по умолчанию)")

    mig_p = sub.add_parser(
        "migrate",
        parents=[parent],
        help="Миграция SQLite -> Lance; см. docs/CONFIG_SCHEMA.md",
    )
    mig_p.add_argument(
        "--dummy-embeddings",
        action="store_true",
        help="Без PyTorch: векторы из хеша текста (см. QUICKSTART). Семантический поиск не будет работать.",
    )
    mig_p.add_argument(
        "--hash-dim",
        type=int,
        default=384,
        metavar="N",
        help="Размерность для --dummy-embeddings (по умолчанию 384, как all-MiniLM-L6-v2)",
    )



    args = parser.parse_args()

    if getattr(args, "command", None) is None:

        args.command = "run"



    if args.command == "migrate":

        _run_migrate_cli(args)

        return



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





def _run_migrate_cli(args: argparse.Namespace) -> None:

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:

        from iskra.migrate import run_migrate



        n = run_migrate(
            args.config,
            dummy_embeddings=getattr(args, "dummy_embeddings", False),
            hash_embedding_dim=int(getattr(args, "hash_dim", 384)),
        )

        print(f"migrate: перенесено записей: {n}", file=sys.stderr)

    except FileNotFoundError as e:

        print(e, file=sys.stderr)

        sys.exit(1)

    except ImportError as e:

        print(f"migrate: {e}", file=sys.stderr)

        print("Установите: pip install iskra[memory]", file=sys.stderr)

        sys.exit(1)

    except (ValidationError, ValueError) as e:

        print(f"Configuration error: {e}", file=sys.stderr)

        sys.exit(1)





if __name__ == "__main__":

    main()

