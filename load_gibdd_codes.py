"""
Модуль для загрузки кодов ГИБДД и геометрии в таблицу gibdd_codes_buffer.

1. Получает список регионов из API ГИБДД.
2. Для каждого региона получает список муниципалитетов (районов, городов).
3. Сохраняет данные в gibdd_codes_buffer: название, код региона, код муниципалитета, геометрию.
Скрипт одноразовый, не включается в main.py.
"""

import requests
import json
import time
from datetime import datetime
from logger_config import setup_logging
from db import df_to_sql, get_engine
import pandas as pd

logger = setup_logging()
engine = get_engine()


def get_regions():
    """
    Получает список регионов из API ГИБДД.
    Возвращает список словарей с id и name.
    """
    now = datetime.now()
    year = now.year
    month = now.month - 1 if now.month > 1 else 12
    if month == 12:
        year -= 1

    payload = {
        "maptype": 1,
        "region": "877",
        "date": f'["MONTHS:{month}.{year}"]',
        "pok": "1"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }

    logger.info("Запрос списка регионов...")
    response = requests.post(
        "http://stat.gibdd.ru/map/getMainMapData",
        json=payload,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        logger.error(f"Ошибка при получении регионов: {response.status_code}")
        return []

    result = response.json()
    metabase = json.loads(result["metabase"])
    maps_data = json.loads(metabase[0]["maps"])
    logger.info(f"Получено {len(maps_data)} регионов")
    return maps_data


def get_districts(region_id, region_name, year, month):
    """
    Получает список муниципалитетов для региона.
    Возвращает список словарей с id, name, path.
    """
    payload = {
        "maptype": 1,
        "region": region_id,
        "date": f'["MONTHS:{month}.{year}"]',
        "pok": "1"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(
            "http://stat.gibdd.ru/map/getMainMapData",
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            logger.error(
                f"Ошибка {response.status_code} для региона {region_name}")
            return []

        result = response.json()
        metabase = json.loads(result["metabase"])
        maps_data = json.loads(metabase[0]["maps"])
        return maps_data

    except Exception as e:
        logger.error(f"Исключение при запросе региона {region_name}: {e}")
        return []


def main():
    logger.info("=" * 60)
    logger.info("ЗАГРУЗКА КОДОВ ГИБДД В ТАБЛИЦУ gibdd_codes_buffer")
    logger.info("=" * 60)

    # Определяем год и месяц для API (всегда предыдущий месяц)
    now = datetime.now()
    year = now.year
    month = now.month - 1 if now.month > 1 else 12
    if month == 12:
        year -= 1
    logger.info(f"Используем данные за {month}.{year}")

    # Получаем список регионов
    regions = get_regions()
    if not regions:
        logger.error("Не удалось получить список регионов. Скрипт остановлен.")
        return

    all_records = []

    # Обрабатываем каждый регион
    for i, region in enumerate(regions, 1):
        region_id = region['id']
        region_name = region['name']
        logger.info(
            f"[{i}/{len(regions)}] Регион: {region_name} (id: {region_id})")

        # Получаем муниципалитеты региона
        districts = get_districts(region_id, region_name, year, month)

        if not districts:
            logger.warning(f"  Муниципалитеты не найдены")
            continue

        logger.info(f"  Найдено муниципалитетов: {len(districts)}")

        # Формируем записи для вставки
        for district in districts:
            all_records.append({
                'city': district['name'],
                'gibdd_region_id': region_id,
                'gibdd_codes': district['id'],
                'path': district.get('path', None)
            })

        # Пауза между регионами, чтобы не перегружать API
        time.sleep(0.5)

    # Сохраняем все записи в БД одной вставкой
    if all_records:
        df = pd.DataFrame(all_records)
        logger.info(f"Всего записей для вставки: {len(df)}")
        try:
            df_to_sql(df, 'gibdd_codes_buffer',
                      if_exists='append', chunksize=500)
            logger.info("Данные успешно загружены в gibdd_codes_buffer")
        except Exception as e:
            logger.error(f"Ошибка при вставке данных: {e}")
    else:
        logger.warning("Нет данных для загрузки")


if __name__ == "__main__":
    main()
