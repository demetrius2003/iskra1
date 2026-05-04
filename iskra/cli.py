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

    parent_cfg = argparse.ArgumentParser(add_help=False)

    parent_cfg.add_argument(

        "--config",

        default="config.yaml",

        help="Path to config.yaml (default: ./config.yaml)",

    )

    parent_run = argparse.ArgumentParser(parents=[parent_cfg], add_help=False)

    parent_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Один проход: промпты в лог (INFO); без LLM, записи в память и events.jsonl",
    )



    parser = argparse.ArgumentParser(

        description="Iskra-1 - autonomous thought loop for LLMs",

        parents=[parent_run],

    )

    sub = parser.add_subparsers(dest="command", required=False)



    sub.add_parser("run", parents=[parent_run], help="Запуск основного цикла (по умолчанию)")

    mig_p = sub.add_parser(
        "migrate",
        parents=[parent_cfg],
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

    dash_p = sub.add_parser(
        "dashboard",
        parents=[parent_cfg],
        help="Статический HTML из events.jsonl (Chart.js); см. QUICKSTART",
    )
    dash_p.add_argument(
        "--hours",
        type=float,
        default=24.0,
        metavar="H",
        help="Окно времени назад от текущего момента UTC (по умолчанию 24)",
    )
    dash_p.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="Куда сохранить HTML (по умолчанию <data_dir>/dashboard.html)",
    )
    dash_p.add_argument(
        "--events",
        default=None,
        metavar="PATH",
        help="Путь к JSONL (по умолчанию logging.event_log.path из конфига)",
    )

    sum_p = sub.add_parser(
        "summary",
        parents=[parent_cfg],
        help="Текстовое резюме событий -> daily_summary.txt",
    )
    sum_p.add_argument("--hours", type=float, default=24.0, metavar="H")
    sum_p.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="Файл вывода (по умолчанию <data_dir>/daily_summary.txt)",
    )
    sum_p.add_argument("--events", default=None, metavar="PATH")

    hook_p = sub.add_parser(
        "webhook",
        parents=[parent_cfg],
        help="HTTP POST -> запись текста во внешний файл ввода (localhost; см. QUICKSTART)",
    )
    hook_p.add_argument("--host", default="127.0.0.1", metavar="ADDR")
    hook_p.add_argument("--port", type=int, default=8765, metavar="N")
    hook_p.add_argument(
        "--target",
        default=None,
        metavar="PATH",
        help="UTF-8 файл (по умолчанию general.external_input_file из конфига)",
    )



    args = parser.parse_args()

    if getattr(args, "command", None) is None:

        args.command = "run"



    if args.command == "migrate":

        _run_migrate_cli(args)

        return

    if args.command == "dashboard":

        _run_dashboard_cli(args)

        return

    if args.command == "summary":

        _run_summary_cli(args)

        return

    if args.command == "webhook":

        _run_webhook_cli(args)

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

    from iskra.logging_support import configure_root_logging

    configure_root_logging(
        level,
        config.logging.format,
        color_primp=config.logging.highlight_primp_logs,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)



    loop = MainLoop(config)

    dry_run = bool(getattr(args, "dry_run", False))

    try:

        asyncio.run(loop.run(dry_run=dry_run))

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





def _run_dashboard_cli(args: argparse.Namespace) -> None:

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:

        from pathlib import Path

        from iskra.experience import write_dashboard

        cfg = load_config(args.config)

        events = Path(args.events or cfg.logging.event_log.path)

        out_raw = args.output

        out = Path(out_raw) if out_raw else Path(cfg.general.data_dir) / "dashboard.html"

        n = write_dashboard(events_path=events, output_path=out, hours=float(args.hours))

        print(f"dashboard: событий в окне: {n} -> {out.resolve()}", file=sys.stderr)

    except FileNotFoundError as e:

        print(e, file=sys.stderr)

        sys.exit(1)

    except (ValidationError, ValueError) as e:

        print(f"Configuration error: {e}", file=sys.stderr)

        sys.exit(1)



def _run_summary_cli(args: argparse.Namespace) -> None:

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:

        from pathlib import Path

        from iskra.experience import write_daily_summary

        cfg = load_config(args.config)

        events = Path(args.events or cfg.logging.event_log.path)

        out_raw = args.output

        out = Path(out_raw) if out_raw else Path(cfg.general.data_dir) / "daily_summary.txt"

        n = write_daily_summary(events_path=events, output_path=out, hours=float(args.hours))

        print(f"summary: событий в окне: {n} -> {out.resolve()}", file=sys.stderr)

    except FileNotFoundError as e:

        print(e, file=sys.stderr)

        sys.exit(1)

    except (ValidationError, ValueError) as e:

        print(f"Configuration error: {e}", file=sys.stderr)

        sys.exit(1)



def _run_webhook_cli(args: argparse.Namespace) -> None:

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:

        from pathlib import Path

        from iskra.experience import run_webhook_server

        cfg = load_config(args.config)

        target = args.target or cfg.general.external_input_file

        if not target:

            print(
                "webhook: задайте --target или general.external_input_file в конфиге",
                file=sys.stderr,
            )

            sys.exit(1)

        run_webhook_server(
            target_file=Path(target),
            host=str(args.host),
            port=int(args.port),
        )

    except FileNotFoundError as e:

        print(e, file=sys.stderr)

        sys.exit(1)

    except (ValidationError, ValueError) as e:

        print(f"Configuration error: {e}", file=sys.stderr)

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

