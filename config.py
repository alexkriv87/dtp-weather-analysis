# config.py
"""
Конфигурационный файл проекта.

Хранит настройки:
- CITIES: список городов для загрузки
- START_DATE: начальная дата загрузки (в формате ГГГГ-ММ-ДД)
- TIMEZONE_OFFSET: смещение часовых поясов для городов (от UTC)

Параметры можно переопределить через командную строку:
    python main.py --cities Москва,Балашиха --start-date 2020-01-01
"""

import argparse


def parse_args():
    """Парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Настройки загрузки данных")
    parser.add_argument("--cities", type=str, help="Города через запятую")
    parser.add_argument("--start-date", type=str,
                        help="Дата начала в формате ГГГГ-ММ-ДД")
    args, unknown = parser.parse_known_args()
    return args


# ============================================
# ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ
# ============================================

DEFAULT_CITIES = ["Балашиха", "Новосибирск"]
DEFAULT_START_DATE = "2025-12-01"


# ============================================
# ИТОГОВЫЕ НАСТРОЙКИ
# ============================================

args = parse_args()

CITIES = args.cities.split(',') if args.cities else DEFAULT_CITIES
START_DATE = args.start_date if args.start_date else DEFAULT_START_DATE


# ============================================
# ЧАСОВЫЕ ПОЯСА (смещение от UTC)
# ============================================

TIMEZONE_OFFSET = {
    'Москва': 3,
    'Санкт-Петербург': 3,
    'Новосибирск': 7,
    'Балашиха': 3,
}
