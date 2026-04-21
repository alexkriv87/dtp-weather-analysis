"""
Модуль для получения координат городов через Яндекс.Геокодер.

1. Загружает из БД города, у которых ещё нет координат (latitude IS NULL).
2. Для каждого города запрашивает координаты через API Яндекса.
3. Обновляет поля latitude и longitude в таблице cities_buffer.
"""

import requests
import time
import os
from dotenv import load_dotenv
from logger_config import setup_logging
from db import read_sql, execute_sql

logger = setup_logging()
load_dotenv()

# ============================================
# ЯНДЕКС ГЕОКОДЕР
# ============================================

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


def fetch_coordinates(city_name: str, region_name: str) -> tuple:
    """
    Получение географических координат города через API Яндекс.Геокодера.
    Возвращает (широта, долгота) или (None, None) в случае ошибки.
    """
    search_query = f"{city_name}, {region_name}, Россия"

    try:
        response = requests.get(
            "https://geocode-maps.yandex.ru/1.x",
            params={
                "geocode": search_query,
                "apikey": YANDEX_API_KEY,
                "format": "json",
                "lang": "ru_RU"
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            found = data['response']['GeoObjectCollection']['metaDataProperty']['GeocoderResponseMetaData']['found']

            if int(found) > 0:
                coordinates = data['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['Point']['pos']
                longitude, latitude = coordinates.split()
                return float(latitude), float(longitude)
            else:
                logger.warning(
                    f"Координаты не найдены для запроса: {search_query}")
                return None, None
        else:
            logger.error(
                f"HTTP ошибка {response.status_code} при запросе координат для города {city_name}")
            return None, None

    except Exception as error:
        logger.error(f"Исключение при обработке города {city_name}: {error}")
        return None, None

# ============================================
# ЗАГРУЗКА ГОРОДОВ БЕЗ КООРДИНАТ
# ============================================


logger.info("Загружаем города без координат из БД")
df_cities = read_sql(
    "SELECT id, city, region FROM cities_buffer WHERE latitude IS NULL")

if df_cities.empty:
    logger.info("Города без координат отсутствуют")
    exit()

logger.info(f"Всего найдено городов без координат: {len(df_cities)}")

# ============================================
# ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ
# ============================================

successful = 0
failed = 0

for index, row in df_cities.iterrows():
    city_id = row['id']
    city_name = row['city']
    region = row['region']

    logger.info(f"[{index+1}/{len(df_cities)}] {city_name} ({region})")

    latitude, longitude = fetch_coordinates(city_name, region)

    if latitude and longitude:
        query = f"UPDATE cities_buffer SET latitude = '{latitude}', longitude = '{longitude}' WHERE id = {city_id}"
        try:
            execute_sql(query)
            successful += 1
            logger.info(f"  + {latitude}, {longitude}")
        except Exception as e:
            failed += 1
            logger.error(f"  Ошибка БД при обновлении: {e}")
    else:
        failed += 1
        logger.warning(f"  Координаты не найдены")

    time.sleep(0.5)

# ============================================
# ИТОГОВАЯ СТАТИСТИКА
# ============================================

logger.info(
    f"Геокодирование завершено. Всего: {len(df_cities)}, успешно: {successful}, ошибок: {failed}")
