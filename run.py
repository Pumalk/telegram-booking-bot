"""
Точка входа. Запуск одной командой:

    python run.py

или с указанием конфига клиента:

    python run.py --config config/клиенты/анна-брови/конфиг.yaml

(на Windows можно просто дважды кликнуть запустить-бота.bat)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config_loader import ConfigError, load_config
from db import Database
from handlers_admin import build_admin_router
from handlers_user import build_user_router
from reminders import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

DEFAULT_CONFIG = BASE_DIR / "config" / "клиенты" / "анна-брови" / "конфиг.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Бот записи клиентов (Тариф 1)")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="путь к конфигу клиента (YAML)",
    )
    return parser.parse_args()


async def run(cfg: dict) -> None:
    bot = Bot(token=cfg["токен_бота"])
    dp = Dispatcher(storage=MemoryStorage())

    data_dir = BASE_DIR.parent / "data"
    db = Database(data_dir / f"{cfg['клиент']}.sqlite3")

    # админский роутер регистрируем первым — его команды приоритетнее
    dp.include_router(build_admin_router(cfg, db))
    dp.include_router(build_user_router(cfg, db))

    reminders_task = asyncio.create_task(reminder_loop(bot, cfg, db))
    log.info("Бот запущен | клиент=%s | ниша=%s | БД=%s",
             cfg["клиент"], cfg["ниша"], db.path)
    try:
        await dp.start_polling(bot)
    finally:
        reminders_task.cancel()
        try:
            await reminders_task
        except asyncio.CancelledError:
            pass
        db.close()


def main() -> None:
    args = parse_args()
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        log.error("Ошибка конфигурации: %s", e)
        sys.exit(1)
    try:
        asyncio.run(run(cfg))
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен.")


if __name__ == "__main__":
    main()
