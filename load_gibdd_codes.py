"""
ОДНОРАЗОВЫЙ СКРИПТ: Загружает регионы и муниципалитеты с геометрией из API ГИБДД.

Сохраняет:
- gibdd_regions (id, name, path) — регионы РФ
- gibdd_municipalities (region_id, region_name, municipality_id, municipality_name, path) — районы/города
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


def get_regions(year, month):
    """
    Получает список регионов из API ГИБДД.
    Возвращает список словарей с id, name, path.
    """
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
    Получает список муниципалитетов для региона из API ГИБДД.
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
    logger.info("ЗАГРУЗКА РЕГИОНОВ И МУНИЦИПАЛИТЕТОВ ИЗ API ГИБДД")
    logger.info("=" * 60)

    # Определяем год и месяц для API (всегда предыдущий месяц)
    now = datetime.now()
    year = now.year
    month = now.month - 1 if now.month > 1 else 12
    if month == 12:
        year -= 1
    logger.info(f"Используем данные за {month}.{year}")

    # ============================================
    # 1. ЗАГРУЖАЕМ И СОХРАНЯЕМ РЕГИОНЫ
    # ============================================

    regions = get_regions(year, month)
    if not regions:
        logger.error("Не удалось получить список регионов")
        return

    # Сохраняем регионы в БД
    regions_records = []
    for region in regions:
        regions_records.append({
            'region_id': region['id'],
            'region_name': region['name'],
            'path': region.get('path')
        })

    df_regions = pd.DataFrame(regions_records)
    try:
        df_to_sql(df_regions, 'gibdd_regions',
                  if_exists='append', chunksize=500)
        logger.info(f"Загружено {len(df_regions)} регионов в gibdd_regions")
    except Exception as e:
        logger.error(f"Ошибка при загрузке регионов: {e}")
        return

    # ============================================
    # 2. ЗАГРУЖАЕМ И СОХРАНЯЕМ МУНИЦИПАЛИТЕТЫ
    # ============================================

    municipalities_records = []

    for i, region in enumerate(regions, 1):
        region_id = region['id']
        region_name = region['name']
        logger.info(
            f"[{i}/{len(regions)}] Регион: {region_name} (id: {region_id})")

        districts = get_districts(region_id, region_name, year, month)

        if not districts:
            logger.warning(f"  Муниципалитеты не найдены")
            continue

        logger.info(f"  Найдено муниципалитетов: {len(districts)}")

        for district in districts:
            municipalities_records.append({
                'region_id': region_id,
                'region_name': region_name,
                'municipality_id': district['id'],
                'municipality_name': district['name'],
                'path': district.get('path')
            })

        time.sleep(0.5)  # Пауза между регионами, чтобы не перегружать API

    if municipalities_records:
        df_municipalities = pd.DataFrame(municipalities_records)
        try:
            df_to_sql(df_municipalities, 'gibdd_municipalities',
                      if_exists='append', chunksize=500)
            logger.info(
                f"Загружено {len(df_municipalities)} муниципалитетов в gibdd_municipalities")
        except Exception as e:
            logger.error(f"Ошибка при загрузке муниципалитетов: {e}")
    else:
        logger.warning("Нет данных для загрузки муниципалитетов")


if __name__ == "__main__":
    main()
