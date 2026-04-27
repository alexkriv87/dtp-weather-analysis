# 03_EL_gibdd_codes.py
"""
ИНКРЕМЕНТАЛЬНАЯ ЗАГРУЗКА РЕГИОНОВ И МУНИЦИПАЛИТЕТОВ ИЗ API ГИБДД.

Сохраняет:
- gibdd_regions (region_id, region_name, path) — регионы РФ (только новые)
- gibdd_municipalities (gibdd_region_id, region_name, municipality_id, municipality_name, path) — районы/города (только новые)
Скрипт можно запускать регулярно — дубликаты не создаются.
"""

import requests
import json
import time
from datetime import datetime
from logger_config import setup_logging
from db import df_to_sql, read_sql, execute_sql, get_engine
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
    logger.info(
        "ИНКРЕМЕНТАЛЬНАЯ ЗАГРУЗКА РЕГИОНОВ И МУНИЦИПАЛИТЕТОВ ИЗ API ГИБДД")
    logger.info("=" * 60)

    # Определяем год и месяц для API (всегда предыдущий месяц)
    now = datetime.now()
    year = now.year
    month = now.month - 1 if now.month > 1 else 12
    if month == 12:
        year -= 1
    logger.info(f"Используем данные за {month}.{year}")

    # ============================================
    # 1. ЗАГРУЖАЕМ И СОХРАНЯЕМ РЕГИОНЫ (инкрементально)
    # ============================================

    regions = get_regions(year, month)
    if not regions:
        logger.error("Не удалось получить список регионов")
        return

    # Формируем список записей для DataFrame
    records = []
    for r in regions:
        records.append({
            'region_id': r['id'],
            'region_name': r['name'],
            'path': r.get('path')
        })
    df_regions = pd.DataFrame(records)

    logger.info(f"Всего получено из API: {len(df_regions)} регионов")

    # Загружаем существующие region_id из БД
    df_db_regions = read_sql("SELECT region_id FROM gibdd_regions")

    # Находим новые регионы через merge
    df_merged = df_regions.merge(
        df_db_regions[['region_id']],
        on='region_id',
        how='left',
        indicator=True
    )
    new_regions = df_merged[df_merged['_merge']
                            == 'left_only'].drop(columns=['_merge'])

    logger.info(f"Из них новых для вставки: {len(new_regions)}")
    logger.info(
        f"Пропущено (уже есть в БД): {len(df_regions) - len(new_regions)}")

    if not new_regions.empty:
        try:
            df_to_sql(new_regions, 'gibdd_regions',
                      if_exists='append', chunksize=500)
            logger.info(
                f"Загружено {len(new_regions)} новых регионов в gibdd_regions")
        except Exception as e:
            logger.error(f"Ошибка при загрузке регионов: {e}")
            return
    else:
        logger.info("Новых регионов нет")

    # ============================================
    # 2. ЗАГРУЖАЕМ И СОХРАНЯЕМ МУНИЦИПАЛИТЕТЫ (инкрементально)
    # ============================================

    # Загружаем существующие ключи из БД
    df_db_codes = read_sql(
        "SELECT gibdd_region_id, municipality_id FROM gibdd_municipalities")
    logger.info(f"Загружено существующих записей в БД: {len(df_db_codes)}")

    # Получаем свежие данные из API
    municipalities_records = []
    for region in regions:
        region_id = region['id']
        region_name = region['name']
        logger.info(f"Обработка региона: {region_name} (id: {region_id})")

        districts = get_districts(region_id, region_name, year, month)

        if not districts:
            logger.warning(f"  Муниципалитеты не найдены")
            continue

        logger.info(f"  Найдено муниципалитетов: {len(districts)}")

        for district in districts:
            municipalities_records.append({
                'gibdd_region_id': region_id,
                'region_name': region_name,
                'municipality_id': district['id'],
                'municipality_name': district['name'],
                'path': district.get('path')
            })

        time.sleep(0.5)

    if not municipalities_records:
        logger.warning("Нет данных для загрузки муниципалитетов")
        return

    df_api_codes = pd.DataFrame(municipalities_records)
    logger.info(f"Всего получено из API: {len(df_api_codes)} муниципалитетов")

    # Находим новые муниципалитеты через merge
    df_merged = df_api_codes.merge(
        df_db_codes[['gibdd_region_id', 'municipality_id']],
        on=['gibdd_region_id', 'municipality_id'],
        how='left',
        indicator=True
    )
    new_municipalities = df_merged[df_merged['_merge'] == 'left_only'].drop(columns=[
                                                                            '_merge'])

    logger.info(f"Из них новых для вставки: {len(new_municipalities)}")
    logger.info(
        f"Пропущено (уже есть в БД): {len(df_api_codes) - len(new_municipalities)}")

    if not new_municipalities.empty:
        try:
            df_to_sql(new_municipalities, 'gibdd_municipalities',
                      if_exists='append', chunksize=500)
            logger.info(
                f"Загружено {len(new_municipalities)} новых муниципалитетов в gibdd_municipalities")
        except Exception as e:
            logger.error(f"Ошибка при загрузке муниципалитетов: {e}")
    else:
        logger.info("Нет новых муниципалитетов для загрузки")


try:
    main()
except Exception as e:
    logger.critical(f"Критическая ошибка в скрипте: {e}")
    import traceback
    logger.critical(traceback.format_exc())
