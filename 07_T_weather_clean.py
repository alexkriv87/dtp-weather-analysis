# 07_T_weather_clean.py
"""
Модуль для нормализации погодных данных.

1. Загружает данные из weather_buffer (с уже проставленным city_id).
2. Загружает существующие временные метки из weather_clean.
3. Фильтрует новые записи через merge.
4. Преобразует типы данных (to_float).
5. Вычисляет местное время (time_local) по часовому поясу города.
6. Сохраняет данные в weather_clean пачками по 500 строк.
"""

import pandas as pd
from datetime import timedelta
from logger_config import setup_logging
from db import read_sql, df_to_sql
from config import TIMEZONE_OFFSET

logger = setup_logging()


def to_float(value):
    """
    Преобразует строку в float, обрабатывая None и 'nan'.
    """
    if value is None or value == 'nan':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def main():
    logger.info("=" * 60)
    logger.info("НОРМАЛИЗАЦИЯ ПОГОДНЫХ ДАННЫХ")
    logger.info("=" * 60)

    # ============================================
    # 1. ЗАГРУЖАЕМ ВСЕ ЗАПИСИ ИЗ БУФЕРА
    # ============================================

    logger.info("Загружаем записи из weather_buffer")
    df_buffer = read_sql("SELECT * FROM weather_buffer")
    if df_buffer.empty:
        logger.info("Нет данных в weather_buffer")
        return
    logger.info(f"Загружено из буфера: {len(df_buffer)} записей")
    # Приводим time к datetime (без часового пояса)
    df_buffer['time'] = pd.to_datetime(df_buffer['time'], utc=False)

    # ============================================
    # 2. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ ВРЕМЕННЫЕ МЕТКИ ИЗ weather_clean
    # ============================================

    logger.info("Загружаем существующие записи из weather_clean")
    df_count = read_sql("SELECT COUNT(*) as cnt FROM weather_clean")
    total_existing = df_count.iloc[0]['cnt'] if not df_count.empty else 0
    logger.info(f"Уже загружено записей в weather_clean: {total_existing}")

    # Загружаем уникальные временные метки для фильтрации
    df_existing = read_sql("SELECT DISTINCT time_utc FROM weather_clean")
    if not df_existing.empty:
        df_existing['time_utc'] = pd.to_datetime(
            df_existing['time_utc'], utc=False)
    existing_timestamps = set(
        df_existing['time_utc']) if not df_existing.empty else set()

    # ============================================
    # 3. ФИЛЬТРУЕМ НОВЫЕ ЗАПИСИ (через merge)
    # ============================================

    logger.info("Фильтруем новые записи")
    # Если existing_timestamps пустое, создаём пустой DataFrame
    if existing_timestamps:
        # Переименовываем колонку для merge
        df_existing_rename = df_existing.rename(columns={'time_utc': 'time'})
        df_merged = df_buffer.merge(
            df_existing_rename[['time']],
            on='time',
            how='left',
            indicator=True
        )
        df_new = df_merged[df_merged['_merge'] ==
                           'left_only'].drop(columns=['_merge'])
    else:
        df_new = df_buffer.copy()

    logger.info(f"Найдено новых записей: {len(df_new)}")

    if df_new.empty:
        logger.info("Новых записей нет")
        return

    # ============================================
    # 4. ПРЕОБРАЗУЕМ ТИПЫ ДАННЫХ
    # ============================================

    logger.info("Преобразуем типы данных")

    # Колонки для преобразования в float
    float_cols = [
        'temperature_2m', 'apparent_temperature', 'precipitation', 'rain',
        'snowfall', 'snow_depth', 'wind_speed_10m', 'wind_gusts_10m',
        'wind_direction_10m', 'cloud_cover', 'is_day', 'weather_code',
        'visibility', 'soil_temperature_0cm'
    ]

    for col in float_cols:
        if col in df_new.columns:
            df_new[col] = df_new[col].apply(to_float)

    # ============================================
    # 5. ВЫЧИСЛЯЕМ МЕСТНОЕ ВРЕМЯ
    # ============================================

    logger.info("Вычисляем местное время")
    # Убеждаемся, что time в нужном формате
    df_new['time_utc'] = pd.to_datetime(df_new['time'], utc=False)
    df_new['time_local'] = df_new.apply(
        lambda row: row['time_utc'] +
        timedelta(hours=TIMEZONE_OFFSET.get(row['city'], 0)),
        axis=1
    )
    df_new['time_local'] = df_new['time_local'].dt.strftime(
        '%Y-%m-%dT%H:%M:%S')
    df_new['time_utc'] = df_new['time_utc'].dt.strftime('%Y-%m-%dT%H:%M:%S')

    # ============================================
    # 6. ПОДГОТОВКА ДАННЫХ ДЛЯ ВСТАВКИ
    # ============================================

    logger.info("Подготавливаем данные для вставки")

    # Выбираем нужные колонки и переименовываем
    df_to_insert = df_new[[
        'city_id', 'time_utc', 'time_local',
        'temperature_2m', 'apparent_temperature', 'precipitation', 'rain',
        'snowfall', 'snow_depth', 'wind_speed_10m', 'wind_gusts_10m',
        'wind_direction_10m', 'cloud_cover', 'is_day', 'weather_code',
        'visibility', 'soil_temperature_0cm'
    ]].copy()

    df_to_insert = df_to_insert.rename(
        columns={'temperature_2m': 'temperature'})

    # ============================================
    # 7. ВСТАВКА В weather_clean
    # ============================================

    logger.info("Сохраняем данные в weather_clean")
    try:
        df_to_sql(df_to_insert, 'weather_clean',
                  if_exists='append', chunksize=500)
        logger.info(
            f"Успешно добавлено {len(df_to_insert)} записей в weather_clean")
    except Exception as e:
        logger.error(f"Ошибка при вставке: {e}")


try:
    main()
except Exception as e:
    logger.critical(f"Критическая ошибка: {e}")
    import traceback
    logger.critical(traceback.format_exc())
