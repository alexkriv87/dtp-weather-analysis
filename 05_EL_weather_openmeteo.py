# 05_EL_weather_openmeteo.py
"""
Модуль для загрузки почасовых погодных данных из Open-Meteo.

1. Загружает координаты и city_id городов из cities_clean.
2. Определяет недостающие даты (которых нет в weather_buffer).
3. Группирует недостающие даты в непрерывные диапазоны.
4. Загружает данные отрезками по 60 дней через API Open-Meteo.
5. Сохраняет данные в weather_buffer вместе с city_id.
"""

import openmeteo_requests
import pandas as pd
from retry_requests import retry
import requests
from datetime import datetime, timedelta
import time
import sys
from logger_config import setup_logging
from db import read_sql, df_to_sql, get_engine
from config import CITIES, START_DATE

logger = setup_logging()
engine = get_engine()

# ============================================
# НАСТРОЙКА OPEN-METEO КЛИЕНТА
# ============================================

# Сессия с автоматическими повторами при ошибках (10 попыток, пауза растет)
retry_session = retry(requests.Session(), retries=10, backoff_factor=0.5)
openmeteo = openmeteo_requests.Client(session=retry_session)


# ============================================
# ФУНКЦИИ ПОЛУЧЕНИЯ ДАННЫХ
# ============================================

def get_city_info(city_name):
    """
    Получает id, координаты города из таблицы cities_clean.
    Возвращает (city_id, latitude, longitude) или (None, None, None).
    """
    query = f"SELECT id, latitude, longitude FROM cities_clean WHERE city = '{city_name}'"
    df = read_sql(query)
    if not df.empty:
        return df.iloc[0]['id'], df.iloc[0]['latitude'], df.iloc[0]['longitude']
    return None, None, None


def get_existing_dates(city_name):
    """
    Возвращает множество дат (YYYY-MM-DD), которые уже есть в weather_buffer для города.
    """
    query = f"""
        SELECT DISTINCT time::date as date
        FROM weather_buffer
        WHERE city = '{city_name}'
    """
    df = read_sql(query)
    if df.empty:
        return set()
    return set(pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'))


def fetch_weather_data(city_name, lat, lon, start_date, end_date):
    """
    Запрашивает данные из Open-Meteo за указанный период.
    Возвращает список записей (словарей) или пустой список при ошибке.
    """
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

        logger.info(
            f"  Получено {len(records)} записей за {start_date}..{end_date}")
        return records

    except Exception as e:
        logger.error(f"  Ошибка при запросе данных: {e}")
        return []


def save_weather_data(records, city_id):
    """
    Сохраняет записи в weather_buffer через df_to_sql пачками по 500 строк.
    Возвращает количество сохранённых записей.
    """
    if not records:
        return 0
    df = pd.DataFrame(records)
    # Добавляем city_id в DataFrame
    df['city_id'] = city_id
    try:
        df_to_sql(df, 'weather_buffer', if_exists='append', chunksize=500)
        logger.info(f"    Сохранено {len(df)} записей")
        return len(df)
    except Exception as e:
        logger.error(f"  Ошибка при сохранении в БД: {e}")
        return 0


def load_date_range(city_name, city_id, lat, lon, start_date, end_date):
    """
    Загружает один непрерывный диапазон дат, разбивая его на отрезки по 60 дней.
    Возвращает количество сохранённых записей.
    """
    total_saved = 0
    current_start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while current_start <= end:
        current_end = current_start + timedelta(days=59)
        if current_end > end:
            current_end = end

        logger.info(
            f"    Загружаем отрезок: {current_start.date()} - {current_end.date()}")
        records = fetch_weather_data(
            city_name, lat, lon,
            current_start.strftime('%Y-%m-%d'),
            current_end.strftime('%Y-%m-%d')
        )
        saved = save_weather_data(records, city_id)
        total_saved += saved

        current_start = current_end + timedelta(days=1)
        time.sleep(30)

    return total_saved


# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================

def main():
    logger.info("=" * 60)
    logger.info("ЗАГРУЗКА ПОГОДНЫХ ДАННЫХ ИЗ OPEN-METEO")
    logger.info("=" * 60)

    END_DATE = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"Желаемый диапазон: {START_DATE} - {END_DATE}")

    for city_name in CITIES:
        logger.info(f"\nОбработка города: {city_name}")

        # Получаем city_id и координаты
        city_id, lat, lon = get_city_info(city_name)
        if city_id is None:
            logger.warning(
                f"  Город {city_name} не найден в cities_clean, пропускаем")
            continue
        if lat is None:
            logger.warning(
                f"  Координаты не найдены для {city_name}, пропускаем")
            continue

        existing_dates = get_existing_dates(city_name)
        logger.info(f"  Уже загружено дат: {len(existing_dates)}")

        all_dates = set(pd.date_range(START_DATE, END_DATE,
                        freq='D').strftime('%Y-%m-%d'))
        missing_dates = all_dates - existing_dates

        if not missing_dates:
            logger.info("  Все даты уже загружены")
            continue

        logger.info(f"  Недостающих дат: {len(missing_dates)}")

        missing_list = sorted(missing_dates)
        ranges = []
        start_range = missing_list[0]
        prev = start_range

        for date in missing_list[1:]:
            curr = datetime.strptime(date, '%Y-%m-%d')
            prev_dt = datetime.strptime(prev, '%Y-%m-%d')
            if (curr - prev_dt).days > 1:
                ranges.append((start_range, prev))
                start_range = date
            prev = date
        ranges.append((start_range, prev))

        logger.info(
            f"  Найдено {len(ranges)} непрерывных диапазонов для загрузки")

        total_saved = 0
        for start, end in ranges:
            logger.info(f"  Загружаем диапазон: {start} - {end}")
            total_saved += load_date_range(city_name,
                                           city_id, lat, lon, start, end)

        logger.info(
            f"  Всего сохранено для {city_name}: {total_saved} записей")

    logger.info("\n" + "=" * 60)
    logger.info("ЗАГРУЗКА ПОГОДЫ ЗАВЕРШЕНА")
    logger.info("=" * 60)


try:
    main()
except Exception as e:
    logger.critical(f"Критическая ошибка: {e}")
    import traceback
    logger.critical(traceback.format_exc())
    sys.exit(1)
