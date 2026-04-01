import re
import pandas as pd
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
# ФУНКЦИЯ ОЧИСТКИ НАСЕЛЕНИЯ
# ============================================


def clean_population(pop_str):
    """Очищает строку с населением: убирает пробелы и преобразует в число"""
    if pop_str is None or pd.isna(pop_str):
        return None

    # Убираем пробелы
    cleaned = str(pop_str).replace(' ', '')

    # Пробуем преобразовать в число
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        # Если не получилось — возвращаем None
        return None

# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================


def main():
    logger.info("Начинаем обновление cities_clean")

    # ============================================
    # 1. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ ГОРОДА ИЗ cities_clean
    # ============================================

    logger.info("Загружаем существующие города из cities_clean")
    clean_rows = []
    start = 0
    step = 1000

    while True:
        result = supabase.table('cities_clean')\
            .select('*')\
            .range(start, start + step - 1)\
            .execute()

        if not result.data:
            break

        clean_rows.extend(result.data)
        start += step

    logger.info(f"Всего загружено из чистовой: {len(clean_rows)} записей")

    # Создаём множество ключей существующих городов
    existing_keys = set()
    for row in clean_rows:
        key = f"{row['city']};{row['region']}"
        existing_keys.add(key)

    # ============================================
    # 2. ЗАГРУЖАЕМ ВСЕ ГОРОДА ИЗ cities_buffer
    # ============================================

    logger.info("Загружаем города из cities_buffer")
    buffer_rows = []
    start = 0

    while True:
        result = supabase.table('cities_buffer')\
            .select('*')\
            .range(start, start + step - 1)\
            .execute()

        if not result.data:
            break

        buffer_rows.extend(result.data)
        start += step

    if not buffer_rows:
        logger.error("Нет данных в cities_buffer")
        return

    logger.info(f"Всего загружено из буфера: {len(buffer_rows)} записей")

    # Создаём множество ключей для буфера
    buffer_keys = set()
    for row in buffer_rows:
        key = f"{row['city']};{row['region']}"
        buffer_keys.add(key)

    # ============================================
    # 3. НАХОДИМ НОВЫЕ ГОРОДА
    # ============================================

    logger.info("Ищем новые города")

    # Новые города = ключи из буфера, которых нет в чистовой
    new_keys = buffer_keys - existing_keys
    logger.info(f"Найдено новых городов: {len(new_keys)}")

    if not new_keys:
        logger.info("Новых городов нет, работа завершена")
        return

    # ============================================
    # 4. ПОДГОТАВЛИВАЕМ ТОЛЬКО НОВЫЕ ГОРОДА
    # ============================================

    logger.info("Подготавливаем данные для новых городов")
    records = []

    # Проходим по всем городам из буфера
    for row in buffer_rows:
        key = f"{row['city']};{row['region']}"

        # Если город новый - обрабатываем
        if key in new_keys:
            # Очищаем population
            population = clean_population(row['population'])

            # Преобразуем координаты в числа
            try:
                latitude = float(row['latitude'])
                longitude = float(row['longitude'])
            except (ValueError, TypeError):
                latitude = None
                longitude = None

            record = {
                'city': row['city'],
                'region': row['region'],
                'federal': row['federal'],
                'population': population,
                'founded_or_first_mentioned': row['founded_or_first_mentioned'],
                'status': row['status'],
                'old_names': row['old_names'],
                'latitude': latitude,
                'longitude': longitude,
                'gibdd_codes': row['gibdd_codes'],
                'gibdd_region_id': row['gibdd_region_id'],
                'gibdd_type': row['gibdd_type']
            }
            records.append(record)

    logger.info(f"Подготовлено к вставке: {len(records)} записей")

    # ============================================
    # 5. ВСТАВЛЯЕМ НОВЫЕ ГОРОДА
    # ============================================

    logger.info("Вставляем новые города в cities_clean")
    total_inserted = 0
    for record in records:
        try:
            result = supabase.table('cities_clean').insert(record).execute()
            if result.data:
                total_inserted += 1
                logger.info(
                    f"Город {record['city']} ({record['region']}) сохранен")
        except Exception as e:
            logger.error(f"Ошибка при вставке города {record['city']}: {e}")

    logger.info(
        f"Всего сохранено в cities_clean: {total_inserted} новых записей")


if __name__ == "__main__":
    main()
