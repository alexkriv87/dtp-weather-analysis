"""
Модуль для нормализации городов и добавления кодов ГИБДД.

Что делает скрипт:
1. Реализует инкрементальную загрузку городов: добавляет только новые записи, которых ещё нет в cities_clean.
2. Загружает города из буферной таблицы (cities_buffer) и чистовой (cities_clean).
3. Находит новые города (которых нет в cities_clean) и добавляет их.
4. Загружает справочник муниципалитетов из gibdd_municipalities.
5. Очищает названия муниципалитетов от приставки "г." и пробелов.
6. Автоматически создаёт записи для городов федерального значения (region_name начинается с "г.") из их районов.
7. Сопоставляет города из cities_clean с муниципалитетами по названию.
8. Для найденных соответствий массово обновляет коды ГИБДД в cities_clean.
"""

import pandas as pd
import traceback
from logger_config import setup_logging
from db import read_sql, df_to_sql, execute_sql, get_engine

logger = setup_logging()
engine = get_engine()

# Константа для имени временной таблицы
TEMP_TABLE_NAME = 'temp_codes_update'


def clean_population(pop_str):
    """Очищает строку с населением: убирает пробелы и преобразует в число"""
    if pop_str is None or pd.isna(pop_str):
        return None
    cleaned = str(pop_str).replace(' ', '')
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def main():
    logger.info("=" * 60)
    logger.info("ЭТАП 1: Нормализация городов (добавление новых городов)")
    logger.info("=" * 60)

    # 1. Загружаем все города из чистовой таблицы
    cities_clean_df = read_sql("SELECT city, region FROM cities_clean")
    clean_city_region = set(
        cities_clean_df['city'] + ';' + cities_clean_df['region'])
    logger.info(f"Загружено из чистовой: {len(cities_clean_df)} записей")

    # 2. Загружаем все города из буфера
    cities_buffer_df = read_sql("SELECT * FROM cities_buffer")
    if cities_buffer_df.empty:
        logger.error("Нет данных в cities_buffer")
        return
    logger.info(f"Загружено из буфера: {len(cities_buffer_df)} записей")
    buffer_city_region = cities_buffer_df['city'] + \
        ';' + cities_buffer_df['region']

    # 3. Находим новые города
    new_city_region = set(buffer_city_region) - clean_city_region

    if new_city_region:
        # Фильтруем DataFrame, оставляя только новые города
        mask = buffer_city_region.isin(new_city_region)
        new_cities_buffer_df = cities_buffer_df[mask].copy()

        # Преобразуем координаты в числа (ошибки заменяем на NaN, затем на None)
        new_cities_buffer_df['latitude'] = pd.to_numeric(
            new_cities_buffer_df['latitude'], errors='coerce')
        new_cities_buffer_df['longitude'] = pd.to_numeric(
            new_cities_buffer_df['longitude'], errors='coerce')

        # Применяем clean_population к колонке population
        new_cities_buffer_df['population'] = new_cities_buffer_df['population'].apply(
            clean_population)

        # Выбираем нужные колонки и создаём DataFrame для вставки
        df_new = new_cities_buffer_df[[
            'city', 'region', 'federal', 'population',
            'founded_or_first_mentioned', 'status', 'old_names',
            'latitude', 'longitude'
        ]].copy()

        try:
            df_to_sql(df_new, 'cities_clean', if_exists='append')
            logger.info(
                f"Добавлено {len(df_new)} новых городов в cities_clean")
        except Exception as e:
            logger.error(f"Ошибка при добавлении городов: {e}")
    else:
        logger.info("Новых городов нет")

    # ============================================
    # ЭТАП 2: Обновление кодов ГИБДД
    # ============================================
    logger.info("=" * 60)
    logger.info("ЭТАП 2: Обновление кодов ГИБДД в cities_clean")
    logger.info("=" * 60)

    # 4. Загружаем города без кодов
    df_no_codes = read_sql(
        "SELECT id, city, region FROM cities_clean WHERE gibdd_codes IS NULL")
    if df_no_codes.empty:
        logger.info("Нет городов без кодов ГИБДД")
        return
    logger.info(f"Найдено городов без кодов: {len(df_no_codes)}")

    # 5. Загружаем все муниципалитеты для поиска
    df_muni = read_sql("""
        SELECT municipality_name, region_name, gibdd_region_id, municipality_id as gibdd_codes
        FROM gibdd_municipalities
    """)
    logger.info(f"Загружено муниципалитетов для поиска: {len(df_muni)}")

    # 6. Очищаем municipality_name от приставки "г." и пробелов
    df_muni['municipality_name'] = (
        df_muni['municipality_name']
        .str.replace('г.', '', regex=False)
        .str.strip()
    )

    # 7. Создаём строки для городов федерального значения
    # Находим все регионы, название которых начинается с "г."
    federal_regions = df_muni[df_muni['region_name'].str.startswith(
        'г.', na=False)]['region_name'].unique().tolist()

    if federal_regions:
        federal_df = df_muni[df_muni['region_name'].isin(
            federal_regions)].copy()

        if not federal_df.empty:
            federal_cities_df = federal_df.groupby(['gibdd_region_id', 'region_name'], as_index=False).agg({
                'gibdd_codes': lambda x: ','.join(x.astype(str))
            })

            name_mapping = {region: region.replace(
                'г.', '').strip() for region in federal_regions}
            federal_cities_df['region_name'] = federal_cities_df['region_name'].map(
                name_mapping)
            federal_cities_df['municipality_name'] = federal_cities_df['region_name']
            federal_cities_df['path'] = None

            df_muni = pd.concat(
                [df_muni, federal_cities_df], ignore_index=True)
            logger.info(
                f"Добавлено {len(federal_cities_df)} строк для городов федерального значения")
    else:
        logger.info("Регионы с 'г.' не найдены")

    # 8. Объединяем (merge) и подготавливаем данные для обновления
    df_merged = df_no_codes.merge(
        df_muni,
        left_on=['city', 'region'],
        right_on=['municipality_name', 'region_name'],
        how='left'
    )

    df_to_update = df_merged[df_merged['gibdd_codes'].notna()].copy()
    logger.info(f"Найдено соответствий: {len(df_to_update)}")

    # 9. Массовое обновление через временную таблицу
    if not df_to_update.empty:
        # Загружаем данные во временную таблицу
        df_to_update[['id', 'gibdd_region_id', 'gibdd_codes']].to_sql(
            TEMP_TABLE_NAME, engine, if_exists='replace', index=False
        )

        # Выполняем массовое обновление
        update_query = f"""
            UPDATE cities_clean AS cc
            SET 
                gibdd_region_id = tmp.gibdd_region_id,
                gibdd_codes = tmp.gibdd_codes,
                updated_at = NOW()
            FROM {TEMP_TABLE_NAME} AS tmp
            WHERE cc.id = tmp.id
        """
        try:
            execute_sql(update_query)
            logger.info(f"Обновлено кодов: {len(df_to_update)}")
        except Exception as e:
            logger.error(f"Ошибка при массовом обновлении: {e}")
        finally:
            # Удаляем временную таблицу
            execute_sql(f"DROP TABLE IF EXISTS {TEMP_TABLE_NAME}")

        # Сохраняем статистику для итогового лога
        updated_count = len(df_to_update)
        not_found_count = len(df_no_codes) - updated_count
    else:
        logger.info("Нет данных для обновления кодов")
        updated_count = 0
        not_found_count = len(df_no_codes)

    logger.info(
        f"Обновление кодов завершено. Обновлено: {updated_count}, не найдено: {not_found_count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Критическая ошибка в скрипте: {e}")
        logger.critical(traceback.format_exc())
