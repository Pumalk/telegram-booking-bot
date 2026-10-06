"""
Загрузка и слияние конфигов: ниша (база) + клиент (переопределения).

Бот собирается из двух YAML-файлов:
  config/ниши/<ниша>.yaml        — базовый шаблон ниши
  config/клиенты/<клиент>/конфиг.yaml — данные конкретного мастера

Клиентский конфиг глубоко перекрывает конфиг ниши, поэтому
менять код бота под нового клиента НЕ нужно.
"""

import re
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Ошибка в конфигурации (файл не найден, нет токена и т.п.)."""


def _read_yaml_mapping(path: Path, description: str) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Не удалось прочитать {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"{description.capitalize()} должен быть YAML-словарём: {path}")
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Рекурсивное слияние: значения override побеждают."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(client_config_path: str | Path) -> dict:
    """Загружает конфиг клиента и подмешивает конфиг его ниши."""
    client_path = Path(client_config_path)
    if not client_path.exists():
        raise ConfigError(f"Не найден файл конфига клиента: {client_path}")

    client_cfg = _read_yaml_mapping(client_path, "конфиг клиента")

    niche_name = client_cfg.get("ниша")
    if not isinstance(niche_name, str) or not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_-]+", niche_name):
        raise ConfigError("Поле «ниша» должно быть коротким именем YAML-шаблона без пути.")

    # config/клиенты/<клиент>/конфиг.yaml -> config/ниши/<ниша>.yaml
    niche_path = client_path.parents[2] / "ниши" / f"{niche_name}.yaml"
    if not niche_path.exists():
        raise ConfigError(f"Не найден конфиг ниши: {niche_path}")

    niche_cfg = _read_yaml_mapping(niche_path, "конфиг ниши")

    cfg = _deep_merge(niche_cfg, client_cfg)
    cfg["_путь"] = str(client_path.resolve())

    _validate(cfg)
    return cfg


def _validate(cfg: dict) -> None:
    client = cfg.get("клиент")
    if not isinstance(client, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", client):
        raise ConfigError("Поле «клиент» должно содержать латинские буквы, цифры, дефис или подчёркивание.")
    token = cfg.get("токен_бота", "")
    if not isinstance(token, str) or not token or "ВСТАВЬТЕ" in token:
        raise ConfigError(
            "В конфиге клиента не указан «токен_бота». "
            "Получите его у @BotFather и вставьте в config клиента."
        )
    admins = cfg.get("админы")
    if (
        not isinstance(admins, list)
        or not admins
        or any(type(admin_id) is not int or admin_id <= 0 for admin_id in admins)
    ):
        raise ConfigError("В конфиге клиента не указаны «админы» (Telegram-ID мастера).")
    services = cfg.get("услуги")
    if not isinstance(services, list) or not services:
        raise ConfigError("В конфиге должен быть список услуг.")
    if not any(isinstance(s, dict) and s.get("включена") for s in services):
        raise ConfigError("Ни одна услуга не включена (услуги: ... включена: true).")
    for service in services:
        if (
            not isinstance(service, dict)
            or not isinstance(service.get("название"), str)
            or not service["название"].strip()
            or type(service.get("цена")) is not int
            or service["цена"] < 0
            or type(service.get("длительность_мин")) is not int
            or service["длительность_мин"] <= 0
            or type(service.get("включена")) is not bool
        ):
            raise ConfigError(
                "У каждой услуги должны быть название, цена >= 0, длительность_мин > 0 "
                "и булево поле «включена»."
            )

    schedule = cfg.get("запись")
    weekdays = {"пн", "вт", "ср", "чт", "пт", "сб", "вс"}
    if (
        not isinstance(schedule, dict)
        or not isinstance(schedule.get("рабочие_дни"), list)
        or not schedule["рабочие_дни"]
        or any(
            not isinstance(weekday, str) or weekday not in weekdays
            for weekday in schedule["рабочие_дни"]
        )
        or type(schedule.get("шаг_слота_мин")) is not int
        or schedule["шаг_слота_мин"] <= 0
    ):
        raise ConfigError("Проверьте в «запись» рабочие_дни и шаг_слота_мин.")
    hours = schedule.get("рабочие_часы")
    match = re.fullmatch(
        r"([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)",
        hours if isinstance(hours, str) else "",
    )
    if not match or tuple(map(int, match.groups()))[0:2] >= tuple(map(int, match.groups()))[2:4]:
        raise ConfigError("Поле «рабочие_часы» должно быть в формате ЧЧ:ММ-ЧЧ:ММ.")
