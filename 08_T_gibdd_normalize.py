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
df_new = df_merged.query('_merge == "left_only"').drop(columns=['_merge'])

logger.info(f"Новых ДТП для обработки: {len(df_new)}")

if df_new.empty:
    logger.info("Новых ДТП нет")
    exit()


# ============================================
# 3. РАЗВОРАЧИВАЕМ JSON В ПЛОСКУЮ ТАБЛИЦУ
# ============================================

def flatten_row(row):
    dtp = json.loads(row['raw_data'])
    df_tmp = pd.json_normalize(dtp)
    df_tmp['buffer_id'] = row['id']
    df_tmp['city_id'] = row['city_id']
    df_tmp['district_id'] = row['district_id']
    return df_tmp


flat_dfs = df_new.apply(flatten_row, axis=1).tolist()
df_flat = pd.concat(flat_dfs, ignore_index=True)
logger.info(
    f"Плоская таблица: {len(df_flat)} строк, {len(df_flat.columns)} колонок")


# ============================================
# 4. ФОРМИРУЕМ ДАТАФРЕЙМЫ ДЛЯ 5 ТАБЛИЦ
# ============================================

main_columns = [
    'KartId', 'date', 'Time', 'DTP_V', 'POG', 'RAN', 'K_TS', 'K_UCH', 'emtp_number',
    'buffer_id', 'city_id', 'district_id'
]
df_main = df_flat[main_columns].copy()

place_columns = [
    'KartId', 'District',
    'infoDtp.n_p', 'infoDtp.street', 'infoDtp.house',
    'infoDtp.k_ul', 'infoDtp.s_pog', 'infoDtp.s_pch', 'infoDtp.osv',
    'infoDtp.COORD_W', 'infoDtp.COORD_L',
    'infoDtp.ndu', 'infoDtp.sdor', 'infoDtp.OBJ_DTP',
    'buffer_id', 'city_id', 'district_id'
]
df_place = df_flat[place_columns].copy()


# ============================================
# 5. РАЗВОРОТ ТРАНСПОРТНЫХ СРЕДСТВ (gibdd_vehicles)
# ============================================

def extract_vehicles(row):
    ts_list = row['infoDtp.ts_info']
    if not ts_list:
        return pd.DataFrame()
    df = pd.json_normalize(ts_list)
    df['kart_id'] = row['KartId']
    df['district_id'] = row['district_id']
    df['city_id'] = row['city_id']
    df['buffer_id'] = row['buffer_id']
    return df


veh_dfs = df_flat.apply(extract_vehicles, axis=1).tolist()
df_vehicles = pd.concat(veh_dfs, ignore_index=True)


# ============================================
# 6. РАЗВОРОТ УЧАСТНИКОВ (explode + json_normalize)
# ============================================

def expand_participants_fast(source_df, source_col, target_df_name):
    if source_df.empty or source_col not in source_df.columns:
        logger.warning(f"Нет данных для разворота участников {target_df_name}")
        return pd.DataFrame()

    s = source_df.explode(source_col).reset_index(drop=True)
    uch_info = pd.json_normalize(s[source_col])

    if target_df_name == "ТС":
        keys_df = s[['kart_id', 'district_id', 'city_id', 'buffer_id']]
        uch_info['vehicle_record_id'] = s.index
    else:
        keys_df = s[['KartId', 'district_id', 'city_id', 'buffer_id']]
        uch_info.rename(columns={'KartId': 'kart_id'}, inplace=True)

    df_participants = pd.concat([keys_df, uch_info], axis=1)
    logger.info(
        f"Развернуто участников {target_df_name}: {len(df_participants)}")
    return df_participants


df_participants_veh = expand_participants_fast(df_vehicles, "ts_uch", "ТС")
df_participants_other = expand_participants_fast(
    df_flat, "infoDtp.uchInfo", "Прочие")


# ============================================
# 7. УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ЗАГРУЗКИ В БД
# ============================================

def prepare_and_save(df, table_name, column_map, required_columns, preprocess_func=None):
    """
    Универсальная подготовка и вставка данных в БД.
    """
    # 1. Переименовываем колонки по словарю
    df_renamed = df.rename(columns=column_map, errors='ignore')

    # 2. Выполняем специфическую предобработку (если передана)
    if preprocess_func:
        df_renamed = preprocess_func(df_renamed)

    # 3. Оставляем только нужные колонки
    cols_exist = [col for col in required_columns if col in df_renamed.columns]
    df_ready = df_renamed[cols_exist].copy()

    # 4. Вставляем в БД
    try:
        df_to_sql(df_ready, table_name, if_exists='append', chunksize=500)
        logger.info(f"Вставлено {len(df_ready)} записей в {table_name}")
    except Exception as e:
        logger.error(f"Ошибка при вставке в {table_name}: {e}")


# ============================================
# 8. ПРЕДОБРАБОТЧИКИ ДЛЯ КАЖДОЙ ТАБЛИЦЫ
# ============================================

def preprocess_main(df):
    """Преобразование типов для main"""
    df['kart_id'] = df['kart_id'].astype(str)
    df['date'] = pd.to_datetime(df['date'], format='%d.%m.%Y', errors='coerce')
    df['time'] = pd.to_datetime(
        df['time'], format='%H:%M', errors='coerce').dt.time
    df['fatalities'] = pd.to_numeric(
        df['fatalities'], errors='coerce').fillna(0).astype(int)
    df['injured'] = pd.to_numeric(
        df['injured'], errors='coerce').fillna(0).astype(int)
    df['vehicles_count'] = pd.to_numeric(
        df['vehicles_count'], errors='coerce').fillna(0).astype(int)
    df['participants_count'] = pd.to_numeric(
        df['participants_count'], errors='coerce').fillna(0).astype(int)
    return df


def preprocess_place(df):
    """Удаляем дублирующую колонку locality (District)"""
    return df.drop(columns=['District'], errors='ignore')


def preprocess_vehicles(df):
    """Замена пустых строк на None в числовых полях"""
    df['year'] = df['year'].replace('', None)
    return df


def preprocess_participants_veh(df):
    """Замена пустых строк на None в числовых полях"""
    if 'driving_experience' in df.columns:
        df['driving_experience'] = df['driving_experience'].replace('', None)
    return df


# ============================================
# 9. ВСТАВКА ДАННЫХ В БД
# ============================================

logger.info("=" * 60)
logger.info("ВСТАВКА ДАННЫХ В ТАБЛИЦЫ")
logger.info("=" * 60)

# 9.1. Основная таблица ДТП
prepare_and_save(
    df=df_main,
    table_name='gibdd_dtp_main',
    column_map={
        'KartId': 'kart_id',
        'date': 'date',
        'Time': 'time',
        'DTP_V': 'dtp_type',
        'POG': 'fatalities',
        'RAN': 'injured',
        'K_TS': 'vehicles_count',
        'K_UCH': 'participants_count',
        'emtp_number': 'emtp_number',
        'buffer_id': 'buffer_id',
        'city_id': 'city_id',
        'district_id': 'district_id'
    },
    required_columns=[
        'kart_id', 'district_id', 'city_id', 'date', 'time', 'dtp_type',
        'fatalities', 'injured', 'vehicles_count', 'participants_count',
        'emtp_number', 'buffer_id'
    ],
    preprocess_func=preprocess_main
)

# 9.2. Место ДТП
prepare_and_save(
    df=df_place,
    table_name='gibdd_dtp_place',
    column_map={
        'KartId': 'kart_id',
        'District': 'locality_tmp',      # временно, чтобы не конфликтовать
        'infoDtp.n_p': 'locality',
        'infoDtp.street': 'street',
        'infoDtp.house': 'house',
        'infoDtp.k_ul': 'road_category',
        'infoDtp.s_pog': 'weather',
        'infoDtp.s_pch': 'road_condition',
        'infoDtp.osv': 'light',
        'infoDtp.COORD_W': 'latitude',
        'infoDtp.COORD_L': 'longitude',
        'infoDtp.ndu': 'road_disadvantages',
        'infoDtp.sdor': 'location_scheme',
        'infoDtp.OBJ_DTP': 'nearby_objects',
        'buffer_id': 'buffer_id',
        'city_id': 'city_id',
        'district_id': 'district_id'
    },
    required_columns=[
        'kart_id', 'district_id', 'city_id', 'locality', 'street', 'house',
        'road_category', 'weather', 'road_condition', 'light',
        'latitude', 'longitude', 'road_disadvantages', 'location_scheme',
        'nearby_objects', 'buffer_id'
    ],
    preprocess_func=preprocess_place
)

# 9.3. Транспортные средства
prepare_and_save(
    df=df_vehicles,
    table_name='gibdd_vehicles',
    column_map={
        'n_ts': 'vehicle_number',
        'ts_s': 'vehicle_status',
        't_ts': 'vehicle_type',
        'marka_ts': 'brand',
        'm_ts': 'model',
        'r_rul': 'drive_type',
        'g_v': 'year',
        'm_pov': 'has_trailer',
        't_n': 'tech_condition',
        'f_sob': 'ownership',
        'o_pf': 'owner_type',
        'buffer_id': 'buffer_id',
        'city_id': 'city_id',
        'district_id': 'district_id',
        'kart_id': 'kart_id'
    },
    required_columns=[
        'kart_id', 'district_id', 'city_id', 'vehicle_number', 'vehicle_status',
        'vehicle_type', 'brand', 'model', 'color', 'drive_type', 'year',
        'has_trailer', 'tech_condition', 'ownership', 'owner_type', 'buffer_id'
    ],
    preprocess_func=preprocess_vehicles
)

# 9.4. Участники в ТС
prepare_and_save(
    df=df_participants_veh,
    table_name='gibdd_participants_veh',
    column_map={
        'K_UCH': 'role',
        'S_T': 'condition',
        'POL': 'gender',
        'V_ST': 'driving_experience',
        'ALCO': 'alcohol',
        'SAFETY_BELT': 'seat_belt',
        'S_SM': 'leaving',
        'N_UCH': 'participant_number',
        'S_SEAT_GROUP': 'seat_group',
        'INJURED_CARD_ID': 'injured_card_id',
        'NPDD': 'violations',
        'SOP_NPDD': 'other_violations',
        'buffer_id': 'buffer_id',
        'city_id': 'city_id',
        'district_id': 'district_id',
        'kart_id': 'kart_id'
    },
    required_columns=[
        'kart_id', 'district_id', 'city_id', 'role', 'condition',
        'gender', 'driving_experience', 'alcohol', 'seat_belt',
        'leaving', 'participant_number', 'seat_group', 'injured_card_id',
        'violations', 'other_violations', 'buffer_id'
    ],
    preprocess_func=preprocess_participants_veh
)

# 9.5. Прочие участники
prepare_and_save(
    df=df_participants_other,
    table_name='gibdd_participants_other',
    column_map={
        'KartId': 'kart_id',
        'K_UCH': 'role',
        'S_T': 'condition',
        'POL': 'gender',
        'ALCO': 'alcohol',
        'S_SM': 'leaving',
        'N_UCH': 'participant_number',
        'NPDD': 'violations',
        'SOP_NPDD': 'other_violations',
        'buffer_id': 'buffer_id',
        'city_id': 'city_id',
        'district_id': 'district_id'
    },
    required_columns=[
        'kart_id', 'district_id', 'city_id', 'role', 'condition',
        'gender', 'alcohol', 'leaving', 'participant_number',
        'violations', 'other_violations', 'buffer_id'
    ]
)

logger.info("=" * 60)
logger.info("НОРМАЛИЗАЦИЯ ДТП ЗАВЕРШЕНА УСПЕШНО")
logger.info("=" * 60)
