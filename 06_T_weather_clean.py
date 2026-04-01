import pandas as pd
from datetime import datetime, timedelta
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
# СЛОВАРЬ ЧАСОВЫХ ПОЯСОВ
# ============================================
# Смещение от UTC в часах
timezone_offset = {
    'Москва': 3,
    'Балашиха': 3
    # при добавлении новых городов - дописывать сюда
}

# ============================================
# ФУНКЦИЯ ПРЕОБРАЗОВАНИЯ ЗНАЧЕНИЙ
# ============================================


def to_float(value):
    """Преобразует строку в float, обрабатывая None и 'nan'"""
    if value is None or value == 'nan':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================


def main():
    logger.info("Начинаем обновление weather_clean")

    # ============================================
    # 1. ЗАГРУЖАЕМ СЛОВАРЬ ГОРОДОВ
    # ============================================

    logger.info("Загружаем города из cities_clean")
    # Словарь: название города -> его id (для быстрого поиска)
    city_dict = {}
    start = 0
    step = 1000

    while True:
        result = supabase.table('cities_clean')\
            .select('id, city')\
            .range(start, start + step - 1)\
            .execute()

        if not result.data:
            break

        for row in result.data:
            city_dict[row['city']] = row['id']

        start += step

    logger.info(f"Загружено городов: {len(city_dict)}")

    # ============================================
    # 2. ПОЛУЧАЕМ СПИСОК ГОРОДОВ ИЗ БУФЕРА (С ПАГИНАЦИЕЙ)
    # ============================================

    logger.info("Получаем список городов из weather_buffer")
    cities = set()
    start = 0
    step = 1000

    while True:
        result = supabase.table('weather_buffer')\
            .select('city')\
            .range(start, start + step - 1)\
            .execute()

        if not result.data:
            break

        for row in result.data:
            cities.add(row['city'])

        start += step

    logger.info(f"Найдено городов в буфере: {len(cities)}")

    # ============================================
    # 3. ОБРАБАТЫВАЕМ КАЖДЫЙ ГОРОД
    # ============================================

    all_inserted = 0  # общий счётчик для всех городов

    for city_name in cities:
        logger.info(f"Обрабатываем город: {city_name}")

        # Получаем city_id по названию города
        city_id = city_dict.get(city_name)
        if not city_id:
            logger.warning(
                f"Город {city_name} не найден в cities_clean, пропускаем")
            continue

        # Получаем смещение часового пояса для города
        offset = timezone_offset[city_name]

        # ============================================
        # 3.1. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ ЗАПИСИ ИЗ weather_clean
        # ============================================

        # Множество временных меток (UTC), которые уже есть в чистовой таблице для этого города
        existing_timestamps = set()
        start = 0

        while True:
            result = supabase.table('weather_clean')\
                .select('time')\
                .eq('city_id', city_id)\
                .range(start, start + step - 1)\
                .execute()

            if not result.data:
                break

            for row in result.data:
                # Отрезаем часовой пояс (+00:00), оставляем чистое UTC время
                clean_time = row['time'].replace('+00:00', '')
                existing_timestamps.add(clean_time)

            start += step

        logger.info(
            f"  Загружено существующих записей из чистовой: {len(existing_timestamps)}")

        # ============================================
        # 3.2. ЗАГРУЖАЕМ ДАННЫЕ ИЗ weather_buffer
        # ============================================

        # Список всех записей из буфера для этого города
        buffer_rows = []
        start = 0

        while True:
            result = supabase.table('weather_buffer')\
                .select('*')\
                .eq('city', city_name)\
                .range(start, start + step - 1)\
                .execute()

            if not result.data:
                break

            buffer_rows.extend(result.data)
            start += step

        logger.info(f"  Загружено из буфера: {len(buffer_rows)} записей")

        # ============================================
        # 3.3. ОТБИРАЕМ НОВЫЕ ЗАПИСИ
        # ============================================

        # Список записей, которые будем вставлять в чистовую таблицу
        new_records = []
        for row in buffer_rows:
            # Проверяем, есть ли уже такая временная метка (UTC)
            if row['time'] in existing_timestamps:
                continue

            # Вычисляем местное время (UTC + смещение)
            dt_utc = datetime.fromisoformat(row['time'])
            dt_local = dt_utc + timedelta(hours=offset)

            # Преобразуем все поля в числа
            record = {
                'city_id': city_id,
                'time': row['time'],
                'time_local': dt_local.isoformat(),
                'temperature': to_float(row['temperature_2m']),
                'apparent_temperature': to_float(row['apparent_temperature']),
                'precipitation': to_float(row['precipitation']),
                'rain': to_float(row['rain']),
                'snowfall': to_float(row['snowfall']),
                'snow_depth': to_float(row['snow_depth']),
                'wind_speed_10m': to_float(row['wind_speed_10m']),
                'wind_gusts_10m': to_float(row['wind_gusts_10m']),
                'wind_direction_10m': to_float(row['wind_direction_10m']),
                'cloud_cover': to_float(row['cloud_cover']),
                'is_day': to_float(row['is_day']),
                'weather_code': to_float(row['weather_code']),
                'visibility': to_float(row['visibility']),
                'soil_temperature_0cm': to_float(row['soil_temperature_0cm'])
            }
            new_records.append(record)

        logger.info(f"  Найдено новых записей: {len(new_records)}")

        # ============================================
        # 3.4. ВСТАВЛЯЕМ НОВЫЕ ЗАПИСИ ПАЧКАМИ
        # ============================================

        if new_records:
            batch_size = 500  # сколько записей вставляем за один раз
            pos = 0  # текущая позиция в списке new_records
            city_inserted = 0  # счётчик для этого города

            while pos < len(new_records):
                end = pos + batch_size
                batch = new_records[pos:end]  # очередная пачка записей

                try:
                    result = supabase.table(
                        'weather_clean').insert(batch).execute()
                    if result.data:
                        city_inserted += len(batch)
                        logger.info(f"    Вставлены записи с {pos} по {end-1}")
                except Exception as e:
                    logger.error(f"    Ошибка при вставке: {e}")

                pos = end  # переходим к следующей пачке

            all_inserted += city_inserted
            logger.info(
                f"  Для города {city_name} добавлено {city_inserted} записей")
        else:
            logger.info(f"  Для города {city_name} новых записей нет")

    # ============================================
    # 4. ИТОГ
    # ============================================

    logger.info(f"Всего добавлено записей в weather_clean: {all_inserted}")


if __name__ == "__main__":
    main()
