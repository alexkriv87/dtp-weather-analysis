"""
Нормализация ДТП из буфера в чистовые таблицы 
"""

import json
import pandas as pd
from logger_config import setup_logging
from db import read_sql, df_to_sql
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

# ============================================
# 6.1. РАЗВОРОТ УЧАСТНИКОВ ТРАНСПОРТНЫХ СРЕДСТВ (ts_uch)
# ============================================

def expand_ts_uch(df_vehicles):
    """
    Разворачивает участников из колонки ts_uch в отдельные строки.
    Каждый участник получает поля из своего ТС.
    """
    rows = []
    for _, veh in df_vehicles.iterrows():
        for uch in veh['ts_uch']:
            # Копируем словарь участника
            row = uch.copy()
            # Добавляем поля из ТС
            row['kart_id'] = veh['kart_id']
            row['district_id'] = veh['district_id']
            row['city_id'] = veh['city_id']
            row['buffer_id'] = veh['buffer_id']
            row['n_ts'] = veh['n_ts']
            row['ts_s'] = veh['ts_s']
            row['t_ts'] = veh['t_ts']
            row['marka_ts'] = veh['marka_ts']
            row['m_ts'] = veh['m_ts']
            row['color'] = veh['color']
            row['r_rul'] = veh['r_rul']
            row['g_v'] = veh['g_v']
            rows.append(row)

    return pd.DataFrame(rows)


df_participants_veh = expand_ts_uch(df_vehicles)
logger.info(f"Участников в ТС: {len(df_participants_veh)}")


# ============================================
# 6.2. РАЗВОРОТ ПРОЧИХ УЧАСТНИКОВ (uchInfo)
# ============================================

def expand_uch_info(df_flat):
    """
    Разворачивает пешеходов и прочих участников из колонки infoDtp.uchInfo.
    Каждый участник получает поля из ДТП.
    """
    rows = []
    for _, row in df_flat.iterrows():
        for uch in row['infoDtp.uchInfo']:
            # Копируем словарь участника
            record = uch.copy()
            # Добавляем поля из ДТП
            record['kart_id'] = row['KartId']
            record['district_id'] = row['district_id']
            record['city_id'] = row['city_id']
            record['buffer_id'] = row['buffer_id']
            rows.append(record)

    return pd.DataFrame(rows)


df_participants_other = expand_uch_info(df_flat)
logger.info(f"Пешеходов/прочих: {len(df_participants_other)}")


# ============================================
# 7. ВСТАВКА ДАННЫХ В БД
# ============================================

logger.info("=" * 60)
logger.info("ВСТАВКА ДАННЫХ В ТАБЛИЦЫ")
logger.info("=" * 60)


# ------------------------------------------------------------
# 7.1. Таблица gibdd_dtp_main
# ------------------------------------------------------------

df_main = df_main.rename(columns={
    'KartId': 'kart_id',
    'Time': 'time',
    'DTP_V': 'dtp_type',
    'POG': 'fatalities',
    'RAN': 'injured',
    'K_TS': 'vehicles_count',
    'K_UCH': 'participants_count'
})

df_main['date'] = pd.to_datetime(
    df_main['date'], format='%d.%m.%Y', errors='coerce')
df_main['time'] = pd.to_datetime(
    df_main['time'], format='%H:%M', errors='coerce').dt.time
df_main['fatalities'] = pd.to_numeric(
    df_main['fatalities'], errors='coerce').fillna(0).astype(int)
df_main['injured'] = pd.to_numeric(
    df_main['injured'], errors='coerce').fillna(0).astype(int)
df_main['vehicles_count'] = pd.to_numeric(
    df_main['vehicles_count'], errors='coerce').fillna(0).astype(int)
df_main['participants_count'] = pd.to_numeric(
    df_main['participants_count'], errors='coerce').fillna(0).astype(int)

main_cols = ['kart_id', 'district_id', 'city_id', 'date', 'time', 'dtp_type',
             'fatalities', 'injured', 'vehicles_count', 'participants_count',
             'emtp_number', 'buffer_id']
df_main = df_main[main_cols]

df_to_sql(df_main, 'gibdd_dtp_main', if_exists='append', chunksize=500)
logger.info(f"Вставлено {len(df_main)} записей в gibdd_dtp_main")


# ------------------------------------------------------------
# 7.2. Таблица gibdd_dtp_place
# ------------------------------------------------------------

df_place = df_place.rename(columns={
    'KartId': 'kart_id',
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
    'infoDtp.OBJ_DTP': 'nearby_objects'
})

if 'District' in df_place.columns:
    df_place = df_place.drop(columns=['District'])

place_cols = ['kart_id', 'district_id', 'city_id', 'locality', 'street', 'house',
              'road_category', 'weather', 'road_condition', 'light',
              'latitude', 'longitude', 'road_disadvantages', 'location_scheme',
              'nearby_objects', 'buffer_id']
df_place = df_place[place_cols]

df_to_sql(df_place, 'gibdd_dtp_place', if_exists='append', chunksize=500)
logger.info(f"Вставлено {len(df_place)} записей в gibdd_dtp_place")


# ------------------------------------------------------------
# 7.3. Таблица gibdd_vehicles
# ------------------------------------------------------------

df_vehicles = df_vehicles.rename(columns={
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
    'o_pf': 'owner_type'
})

df_vehicles['year'] = df_vehicles['year'].replace('', None)

vehicles_cols = ['kart_id', 'district_id', 'city_id', 'vehicle_number', 'vehicle_status',
                 'vehicle_type', 'brand', 'model', 'color', 'drive_type', 'year',
                 'has_trailer', 'tech_condition', 'ownership', 'owner_type', 'buffer_id']
df_vehicles = df_vehicles[vehicles_cols]

df_to_sql(df_vehicles, 'gibdd_vehicles', if_exists='append', chunksize=500)
logger.info(f"Вставлено {len(df_vehicles)} записей в gibdd_vehicles")


# ------------------------------------------------------------
# 7.4. Таблица gibdd_participants_veh
# ------------------------------------------------------------

df_participants_veh = df_participants_veh.rename(columns={
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
    'SOP_NPDD': 'other_violations'
})

if 'driving_experience' in df_participants_veh.columns:
    df_participants_veh['driving_experience'] = df_participants_veh['driving_experience'].replace(
        '', None)

part_veh_cols = ['kart_id', 'district_id', 'city_id', 'role', 'condition', 'gender',
                 'driving_experience', 'alcohol', 'seat_belt', 'leaving', 'participant_number',
                 'seat_group', 'injured_card_id', 'violations', 'other_violations', 'buffer_id']
part_veh_cols_exist = [
    col for col in part_veh_cols if col in df_participants_veh.columns]
df_participants_veh = df_participants_veh[part_veh_cols_exist]

df_to_sql(df_participants_veh, 'gibdd_participants_veh',
          if_exists='append', chunksize=500)
logger.info(
    f"Вставлено {len(df_participants_veh)} записей в gibdd_participants_veh")


# ------------------------------------------------------------
# 7.5. Таблица gibdd_participants_other
# ------------------------------------------------------------

df_participants_other = df_participants_other.rename(columns={
    'KartId': 'kart_id',
    'K_UCH': 'role',
    'S_T': 'condition',
    'POL': 'gender',
    'ALCO': 'alcohol',
    'S_SM': 'leaving',
    'N_UCH': 'participant_number',
    'NPDD': 'violations',
    'SOP_NPDD': 'other_violations'
})

part_other_cols = ['kart_id', 'district_id', 'city_id', 'role', 'condition', 'gender',
                   'alcohol', 'leaving', 'participant_number', 'violations',
                   'other_violations', 'buffer_id']
part_other_cols_exist = [
    col for col in part_other_cols if col in df_participants_other.columns]
df_participants_other = df_participants_other[part_other_cols_exist]

df_to_sql(df_participants_other, 'gibdd_participants_other',
          if_exists='append', chunksize=500)
logger.info(
    f"Вставлено {len(df_participants_other)} записей в gibdd_participants_other")


logger.info("=" * 60)
logger.info("НОРМАЛИЗАЦИЯ ДТП ЗАВЕРШЕНА УСПЕШНО")
logger.info("=" * 60)
