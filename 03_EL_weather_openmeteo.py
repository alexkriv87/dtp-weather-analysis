import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
from logger_config import setup_logging
from supabase import create_client, Client
from datetime import datetime, timedelta
import time
import sys
import os
from dotenv import load_dotenv
from config import CITIES, START_YEAR, START_MONTH

logger = setup_logging()
load_dotenv()

# ============================================
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# НАСТРОЙКА OPEN-METEO КЛИЕНТА
# ============================================

# Кэш чтобы при отладке не дергать API повторно
cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
# Автоповтор при ошибках (10 попыток, пауза растет)
retry_session = retry(cache_session, retries=10, backoff_factor=0.5)
openmeteo = openmeteo_requests.Client(session=retry_session)

# ============================================
# ФУНКЦИИ ПОЛУЧЕНИЯ ДАННЫХ
# ============================================


def get_city_coordinates(city_name):
    """Получает координаты города из cities_buffer"""

    result = supabase.table('cities_buffer')\
        .select('latitude, longitude')\
        .eq('city', city_name)\
        .execute()

    if result.data and len(result.data) > 0:
        return result.data[0]['latitude'], result.data[0]['longitude']
    return None, None


def get_last_date_for_city(city_name):
    """Последняя загруженная дата для инкрементальной загрузки"""

    result = supabase.table('weather_buffer')\
        .select('time')\
        .eq('city', city_name)\
        .order('time', desc=True)\
        .limit(1)\
        .execute()

    if result.data:
        return result.data[0]['time']
    return None


def fetch_weather_data(city_name, lat, lon, start_date, end_date):
    """Запрашивает данные из Open-Meteo за указанный период.
       При критической ошибке завершает работу скрипта."""

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "start_date": start_date,
        "end_date": end_date,
        "hourly": [
            "temperature_2m", "soil_temperature_0cm", "apparent_temperature",
            "precipitation", "rain", "snowfall", "snow_depth",
            "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
            "visibility", "cloud_cover", "is_day", "weather_code"
        ],
        "timezone": "UTC"
    }

    try:
        # Таймаут 5 минут (300 секунд) на ожидание ответа от API
        responses = openmeteo.weather_api(url, params=params, timeout=300)
        response = responses[0]
        hourly = response.Hourly()

        records = []
        for i in range(len(hourly.Variables(0).ValuesAsNumpy())):
            record = {
                "time": pd.to_datetime(hourly.Time() + i * hourly.Interval(), unit="s").isoformat(),
                "city": city_name,
                "temperature_2m": str(hourly.Variables(0).ValuesAsNumpy()[i]),
                "soil_temperature_0cm": str(hourly.Variables(1).ValuesAsNumpy()[i]),
                "apparent_temperature": str(hourly.Variables(2).ValuesAsNumpy()[i]),
                "precipitation": str(hourly.Variables(3).ValuesAsNumpy()[i]),
                "rain": str(hourly.Variables(4).ValuesAsNumpy()[i]),
                "snowfall": str(hourly.Variables(5).ValuesAsNumpy()[i]),
                "snow_depth": str(hourly.Variables(6).ValuesAsNumpy()[i]),
                "wind_speed_10m": str(hourly.Variables(7).ValuesAsNumpy()[i]),
                "wind_gusts_10m": str(hourly.Variables(8).ValuesAsNumpy()[i]),
                "wind_direction_10m": str(hourly.Variables(9).ValuesAsNumpy()[i]),
                "visibility": str(hourly.Variables(10).ValuesAsNumpy()[i]),
                "cloud_cover": str(hourly.Variables(11).ValuesAsNumpy()[i]),
                "is_day": str(hourly.Variables(12).ValuesAsNumpy()[i]),
                "weather_code": str(hourly.Variables(13).ValuesAsNumpy()[i])
            }
            records.append(record)

        logger.info(f"  Получено {len(records)} записей для {city_name}")
        return records

    except Exception as e:
        logger.error(
            f"  КРИТИЧЕСКАЯ ОШИБКА: Open-Meteo не отвечает после 10 попыток")
        logger.error(f"  {e}")
        sys.exit(1)  # Полная остановка скрипта


def save_to_supabase(records, city_name):
    """Сохраняет записи в weather_buffer"""

    if not records:
        return 0

    try:
        result = supabase.table('weather_buffer').insert(records).execute()

        if result.data:
            logger.info(
                f"    Сохранено {len(records)} записей для {city_name}")
            return len(records)
        else:
            logger.warning(
                f"    Нет подтверждения о сохранении для {city_name}")
            return 0

    except Exception as e:
        logger.error(f"  Ошибка при сохранении в Supabase: {e}")
        return 0

# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================


def main():
    # Конфигурация
    city_list = CITIES
    START_DATE = f"{START_YEAR}-{START_MONTH:02d}-01"
    END_DATE = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    logger.info(f"Загрузка погоды за период: {START_DATE} - {END_DATE}")
    total_records = 0

    for city_name in city_list:
        logger.info(f"\nНачинаем загрузку для города: {city_name}")

        # Получаем координаты
        lat, lon = get_city_coordinates(city_name)
        if not lat or not lon:
            logger.warning(f"  Координаты не найдены, пропускаем город")
            continue

        # Корректируем стартовую дату если для города уже есть данные
        city_start = START_DATE
        last_date = get_last_date_for_city(city_name)

        if last_date:
            last = pd.to_datetime(last_date).strftime('%Y-%m-%d')
            if last >= city_start:
                city_start = (pd.to_datetime(last_date) +
                              timedelta(days=1)).strftime('%Y-%m-%d')
                logger.info(
                    f"  Последние данные: {last}, продолжаем с {city_start}")

        # Если всё уже загружено
        if city_start > END_DATE:
            logger.info(f"  Данные уже актуальны до {END_DATE}")
            continue

        # Загружаем отрезками по 60 дней
        current_start = datetime.strptime(city_start, '%Y-%m-%d')
        end = datetime.strptime(END_DATE, '%Y-%m-%d')

        while current_start <= end:
            # 60 дней = start + 59 дней
            current_end = current_start + timedelta(days=59)
            if current_end > end:
                current_end = end

            logger.info(
                f"  Загружаем отрезок: {current_start.strftime('%Y-%m-%d')} - {current_end.strftime('%Y-%m-%d')}")

            # Загружаем данные
            records = fetch_weather_data(city_name, lat, lon,
                                         current_start.strftime('%Y-%m-%d'),
                                         current_end.strftime('%Y-%m-%d'))

            # Сохраняем и сдвигаем дату
            saved = save_to_supabase(records, city_name)
            total_records += saved
            current_start = current_end + timedelta(days=1)

            logger.info(f"  Пауза 30 секунд перед следующим отрезком...")
            time.sleep(30)

        # Пауза между городами
        logger.info(f"Пауза 60 секунд перед следующим городом...")
        time.sleep(60)

    logger.info(f"\nВсего сохранено записей: {total_records}")


if __name__ == "__main__":
    main()
