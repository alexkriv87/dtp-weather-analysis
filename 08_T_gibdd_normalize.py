import json
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
# 1. ПОЛУЧАЕМ УНИКАЛЬНЫЕ ГОРОДА ИЗ БУФЕРА ДТП
# ============================================

logger.info("Получаем список городов из gibdd_dtp_buffer")
cities_in_gibdd = set()
start = 0
step = 1000

while True:
    result = supabase.table('gibdd_dtp_buffer')\
        .select('city')\
        .range(start, start + step - 1)\
        .execute()

    if not result.data:
        break

    for row in result.data:
        if row['city']:
            cities_in_gibdd.add(row['city'])

    start += step

logger.info(f"Найдено уникальных городов в ДТП: {len(cities_in_gibdd)}")

# ============================================
# 2. ДЛЯ КАЖДОГО ГОРОДА ИЩЕМ ID В cities_clean
# ============================================

logger.info("Ищем соответствия в cities_clean")
city_dict = {}

for city_name in cities_in_gibdd:
    result = supabase.table('cities_clean')\
        .select('id')\
        .eq('city', city_name)\
        .execute()

    if len(result.data) > 1:
        logger.warning(f"Найдено несколько городов {city_name}, взят первый")

    if result.data:
        city_dict[city_name] = result.data[0]['id']
        logger.info(f"Город {city_name} → id {result.data[0]['id']}")
    else:
        logger.warning(f"Город {city_name} не найден в cities_clean")

# ============================================
# 3. ЗАГРУЖАЕМ ВСЕ ЗАПИСИ ИЗ БУФЕРА
# ============================================

logger.info("Загружаем все записи из gibdd_dtp_buffer")
buffer_rows = []
start = 0
step = 1000

while True:
    result = supabase.table('gibdd_dtp_buffer')\
        .select('*')\
        .order('id')\
        .range(start, start + step - 1)\
        .execute()

    if not result.data:
        break

    buffer_rows.extend(result.data)
    start += step

logger.info(f"Загружено {len(buffer_rows)} записей из буфера")

if not buffer_rows:
    logger.error("Нет данных в буфере")
    exit()

# ============================================
# 4. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ КЛЮЧИ ДЛЯ ПРОВЕРКИ ДУБЛИКАТОВ
# ============================================

logger.info("Загружаем существующие kart_id из gibdd_dtp_main")
existing_keys = set()
start = 0
step = 1000

while True:
    result = supabase.table('gibdd_dtp_main')\
        .select('kart_id, district_id')\
        .range(start, start + step - 1)\
        .execute()

    if not result.data:
        break

    for row in result.data:
        key = f"{row['kart_id']}_{row['district_id']}"
        existing_keys.add(key)

    start += step

logger.info(f"Загружено существующих записей в main: {len(existing_keys)}")

# ============================================
# 5. ПОДГОТАВЛИВАЕМ ДАННЫЕ
# ============================================

main_batch = []
place_batch = []
vehicles_batch = []
part_veh_batch = []
part_other_batch = []

for row in buffer_rows:
    key = f"{row['kart_id']}_{row['district_id']}"
    if key in existing_keys:
        logger.debug(f"ДТП {row['kart_id']} уже есть, пропускаем")
        continue

    dtp = json.loads(row['raw_data'])
    city_name = row['city']
    city_id = city_dict.get(city_name)

    date_str = dtp['date']
    day, month, year = date_str.split('.')
    formatted_date = f"{year}-{month}-{day}"
    current_dtp_index = len(main_batch)

    # MAIN
    main_record = {
        'kart_id': int(dtp['KartId']),
        'district_id': row['district_id'],
        'city_id': city_id,
        'date': formatted_date,
        'time': dtp['Time'],
        'dtp_type': dtp['DTP_V'],
        'fatalities': int(dtp['POG']) if dtp['POG'] else 0,
        'injured': int(dtp['RAN']) if dtp['RAN'] else 0,
        'vehicles_count': int(dtp['K_TS']) if dtp['K_TS'] else 0,
        'participants_count': int(dtp['K_UCH']) if dtp['K_UCH'] else 0,
        'emtp_number': dtp.get('emtp_number', '')
    }
    main_batch.append(main_record)

    # PLACE
    place_record = {
        'dtp_id': None,
        'locality': dtp.get('District', ''),
        'street': dtp['infoDtp'].get('street', ''),
        'house': dtp['infoDtp'].get('house', ''),
        'road_category': dtp['infoDtp'].get('k_ul', ''),
        'weather': dtp['infoDtp'].get('s_pog', []),
        'road_condition': dtp['infoDtp'].get('s_pch', ''),
        'light': dtp['infoDtp'].get('osv', ''),
        'latitude': float(dtp['infoDtp']['COORD_W']) if dtp['infoDtp'].get('COORD_W') else None,
        'longitude': float(dtp['infoDtp']['COORD_L']) if dtp['infoDtp'].get('COORD_L') else None,
        'road_disadvantages': dtp['infoDtp'].get('ndu', []),
        'location_scheme': dtp['infoDtp'].get('sdor', []),
        'nearby_objects': dtp['infoDtp'].get('OBJ_DTP', [])
    }
    place_batch.append(place_record)

    # VEHICLES и PARTICIPANTS_VEH
    if 'ts_info' in dtp['infoDtp']:
        for ts in dtp['infoDtp']['ts_info']:
            current_veh_index = len(vehicles_batch)

            vehicle_record = {
                'dtp_id': None,
                'vehicle_number': '',
                'vehicle_status': ts.get('ts_s', ''),
                'vehicle_type': ts.get('t_ts', ''),
                'brand': ts.get('marka_ts', ''),
                'model': ts.get('m_ts', ''),
                'color': ts.get('color', ''),
                'drive_type': ts.get('r_rul', ''),
                'year': int(ts['g_v']) if ts.get('g_v') and ts['g_v'].isdigit() else None,
                'has_trailer': ts.get('m_pov', ''),
                'tech_condition': ts.get('t_n', ''),
                'ownership': ts.get('f_sob', ''),
                'owner_type': ts.get('o_pf', '')
            }
            vehicles_batch.append(vehicle_record)

            if 'ts_uch' in ts:
                for uch in ts['ts_uch']:
                    part_veh_record = {
                        'dtp_id': None,
                        'vehicle_id': None,
                        'role': uch.get('K_UCH', ''),
                        'condition': uch.get('S_T', ''),
                        'gender': uch.get('POL', ''),
                        'driving_experience': int(uch['V_ST']) if uch.get('V_ST') and uch['V_ST'].isdigit() else None,
                        'alcohol': uch.get('ALCO', ''),
                        'seat_belt': uch.get('SAFETY_BELT', ''),
                        'leaving': uch.get('S_SM', ''),
                        'participant_number': uch.get('N_UCH', ''),
                        'seat_group': uch.get('S_SEAT_GROUP', ''),
                        'injured_card_id': uch.get('INJURED_CARD_ID', ''),
                        'violations': uch.get('NPDD', []),
                        'other_violations': uch.get('SOP_NPDD', []),
                        '_temp_veh_index': current_veh_index
                    }
                    part_veh_batch.append(part_veh_record)

    # ПЕШЕХОДЫ
    if 'infoDtp' in dtp and 'uchInfo' in dtp['infoDtp'] and dtp['infoDtp']['uchInfo']:
        for uch in dtp['infoDtp']['uchInfo']:
            part_other_record = {
                'dtp_id': None,
                'role': uch.get('K_UCH', ''),
                'condition': uch.get('S_T', ''),
                'gender': uch.get('POL', ''),
                'alcohol': uch.get('ALCO', ''),
                'leaving': uch.get('S_SM', ''),
                'participant_number': uch.get('N_UCH', ''),
                'violations': uch.get('NPDD', []),
                'other_violations': uch.get('SOP_NPDD', []),
                '_temp_dtp_index': current_dtp_index
            }
            part_other_batch.append(part_other_record)

logger.info(f"Подготовлено {len(main_batch)} записей для main")
logger.info(f"Подготовлено {len(place_batch)} записей для place")
logger.info(f"Подготовлено {len(vehicles_batch)} записей для vehicles")
logger.info(f"Подготовлено {len(part_veh_batch)} записей для participants_veh")
logger.info(f"Подготовлено {len(part_other_batch)} записей для participants_other")

# ============================================
# 6. ВСТАВКА ДАННЫХ
# ============================================

if not main_batch:
    logger.info("Новых записей для main нет")
    exit()

try:
    result = supabase.table('gibdd_dtp_main').insert(main_batch).execute()
    if not result.data:
        logger.error("Ошибка при вставке main")
        exit()

    logger.info(f"Вставлено {len(result.data)} записей в main")
    inserted_ids = [row['id'] for row in result.data]

    # PLACE
    if place_batch and len(place_batch) == len(result.data):
        for i, place_record in enumerate(place_batch):
            place_record['dtp_id'] = inserted_ids[i]

        try:
            place_result = supabase.table('gibdd_dtp_place').insert(place_batch).execute()
            if place_result.data:
                logger.info(f"Вставлено {len(place_result.data)} записей в place")
        except Exception as e:
            logger.error(f"Ошибка при вставке place: {e}")

    # VEHICLES
    if vehicles_batch:
        vehicles_by_dtp = []
        veh_index = 0

        for i, main_record in enumerate(main_batch):
            ts_count = main_record['vehicles_count']
            for j in range(ts_count):
                vehicles_by_dtp.append({
                    'index': veh_index + j,
                    'dtp_id': inserted_ids[i]
                })
            veh_index += ts_count

        for item in vehicles_by_dtp:
            vehicles_batch[item['index']]['dtp_id'] = item['dtp_id']

        try:
            veh_result = supabase.table('gibdd_vehicles').insert(vehicles_batch).execute()
            if veh_result.data:
                logger.info(f"Вставлено {len(veh_result.data)} записей в vehicles")

                if part_veh_batch:
                    veh_ids = [row['id'] for row in veh_result.data]

                    for part_record in part_veh_batch:
                        veh_index = part_record.pop('_temp_veh_index')
                        part_record['vehicle_id'] = veh_ids[veh_index]
                        part_record['dtp_id'] = vehicles_batch[veh_index]['dtp_id']

                    try:
                        part_result = supabase.table('gibdd_participants_veh').insert(part_veh_batch).execute()
                        if part_result.data:
                            logger.info(f"Вставлено {len(part_result.data)} записей в participants_veh")
                    except Exception as e:
                        logger.error(f"Ошибка при вставке participants_veh: {e}")

                if part_other_batch:
                    for other_record in part_other_batch:
                        dtp_index = other_record.pop('_temp_dtp_index')
                        other_record['dtp_id'] = inserted_ids[dtp_index]

                    try:
                        other_result = supabase.table('gibdd_participants_other').insert(part_other_batch).execute()
                        if other_result.data:
                            logger.info(f"Вставлено {len(other_result.data)} записей в participants_other")
                    except Exception as e:
                        logger.error(f"Ошибка при вставке participants_other: {e}")

        except Exception as e:
            logger.error(f"Ошибка при вставке vehicles: {e}")

except Exception as e:
    logger.error(f"Ошибка при вставке main: {e}")