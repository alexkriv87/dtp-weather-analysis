# 08_T_gibdd_normalize.py
"""
Нормализация ДТП из буфера в чистовые таблицы (Timeweb версия).
Без Supabase, только SQLAlchemy + pandas.
"""

import json
import pandas as pd
from logger_config import setup_logging
from db import read_sql, df_to_sql, execute_sql, engine
from config import CITIES

logger = setup_logging()

logger.info("=" * 60)
logger.info("НОРМАЛИЗАЦИЯ ДТП (JSON → 5 ТАБЛИЦ)")
logger.info("=" * 60)

# ============================================
# 1. ЗАГРУЗКА БУФЕРА (только нужные города)
# ============================================

cities_str = "', '".join(CITIES)
query = f"""
    SELECT id, kart_id, district_id, city, city_id, raw_data
    FROM gibdd_dtp_buffer
    WHERE city IN ('{cities_str}')
"""
df_buffer = read_sql(query)
logger.info(f"Загружено из буфера: {len(df_buffer)} записей")

if df_buffer.empty:
    logger.info("Нет данных для обработки")
    exit()

# ============================================
# 2. MERGE ПАТТЕРН (находим новые ДТП)
# ============================================

logger.info("Загружаем существующие ключи из gibdd_dtp_main")
df_existing = read_sql("SELECT kart_id, district_id FROM gibdd_dtp_main")
logger.info(f"Уже обработано ДТП: {len(df_existing)}")

df_merged = df_buffer.merge(
    df_existing[['kart_id', 'district_id']],
    on=['kart_id', 'district_id'],
    how='left',
    indicator=True
)
df_new = df_merged[df_merged['_merge'] == 'left_only'].drop(columns=['_merge'])

logger.info(f"Новых ДТП для обработки: {len(df_new)}")

if df_new.empty:
    logger.info("Новых ДТП нет")
    exit()

# ============================================
# ДАЛЬШЕ: разворот JSON, извлечение 5 таблиц, вставка
# ============================================
print(df_new.head(10))
