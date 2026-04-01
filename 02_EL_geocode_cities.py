import requests
import time
import os
from dotenv import load_dotenv
from logger_config import setup_logging
from supabase import create_client, Client

logger = setup_logging()
load_dotenv()

# ============================================
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# ЯНДЕКС ГЕОКОДЕР
# ============================================

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


def fetch_coordinates(city_name: str, region_name: str) -> tuple:
    """
    Получение географических координат города через API Яндекс.Геокодера.

    Args:
        city_name: Наименование населенного пункта
        region_name: Наименование региона

    Returns:
        Кортеж (широта, долгота) или (None, None) в случае ошибки
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

            # Проверка наличия результатов поиска
            found = data['response']['GeoObjectCollection']['metaDataProperty']['GeocoderResponseMetaData']['found']

            if int(found) > 0:
                # Извлечение координат первого найденного объекта
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
# ПОЛУЧЕНИЕ ГОРОДОВ БЕЗ КООРДИНАТ
# ============================================


all_cities = []
start = 0
step = 1000

# Загружаем пачками по 1000 записей (ограничение Supabase)
while True:
    result = supabase.table('cities_buffer')\
        .select('id, city, region')\
        .is_('latitude', 'null')\
        .range(start, start + step - 1)\
        .execute()

    # Выходим из цикла, когда данные закончились
    if not result.data:
        break

    all_cities.extend(result.data)
    start += step
    logger.info(f"Загружено {len(all_cities)} городов без координат")

if not all_cities:
    logger.info("Города без координат отсутствуют")
    exit()

logger.info(f"Всего найдено городов без координат: {len(all_cities)}")

# ============================================
# ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ
# ============================================

successful = 0
failed = 0

for index, city in enumerate(all_cities, 1):
    city_id = city['id']
    city_name = city['city']
    region = city['region']

    logger.info(f"[{index}/{len(all_cities)}] {city_name} ({region})")

    latitude, longitude = fetch_coordinates(city_name, region)

    if latitude and longitude:
        update_result = supabase.table('cities_buffer')\
            .update({'latitude': str(latitude), 'longitude': str(longitude)})\
            .eq('id', city_id)\
            .execute()

        if update_result.data:
            successful += 1
            logger.info(f"  + {latitude}, {longitude}")
        else:
            failed += 1
            logger.error(f"  ошибка БД")
    else:
        failed += 1
        logger.warning(f"  не найдено")

    time.sleep(0.3)

# ============================================
# ИТОГОВАЯ СТАТИСТИКА
# ============================================

logger.info(
    f"Геокодирование завершено. Всего: {len(all_cities)}, успешно: {successful}, ошибок: {failed}, не найдено: {failed}")
