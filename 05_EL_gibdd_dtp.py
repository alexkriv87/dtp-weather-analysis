import requests
import json
import time
from datetime import datetime
import os
from dotenv import load_dotenv
from supabase import create_client
from logger_config import setup_logging
from config import CITIES, START_YEAR, START_MONTH

logger = setup_logging()
load_dotenv()

# ============================================
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# ПОЛУЧЕНИЕ КОДОВ ГИБДД ДЛЯ ГОРОДА
# ============================================


def get_gibdd_codes_for_city(city_name):
    result = supabase.table('cities_buffer')\
        .select('gibdd_region_id, gibdd_codes')\
        .eq('city', city_name)\
        .execute()

    if not result.data:
        return None, None

    row = result.data[0]
    region = row['gibdd_region_id']
    codes_str = row['gibdd_codes']

    if not region or not codes_str:
        return None, None

    return region, codes_str.split(',')

# ============================================
# ЗАПРОС К API ГИБДД
# ============================================


def get_dtp_cards(city_name, year, month, start=1, end=100):
    region, codes_list = get_gibdd_codes_for_city(city_name)

    if region is None:
        return []

    all_dtp = []
    url = "http://stat.gibdd.ru/map/getDTPCardData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    for code in codes_list:
        payload = {
            "data": {
                "date": [f"MONTHS:{month}.{year}"],
                "ParReg": region,
                "order": {"type": "1", "fieldName": "dat"},
                "reg": code,
                "ind": "1",
                "st": str(start),
                "en": str(end),
                "fil": {"isSummary": False},
                "fieldNames": [
                    "dat", "time", "coordinates", "infoDtp", "k_ul", "dor", "ndu",
                    "k_ts", "ts_info", "pdop", "pog", "osv", "s_pch", "s_pog",
                    "n_p", "n_pg", "obst", "sdor", "t_osv", "t_p", "t_s", "v_p", "v_v"
                ]
            }
        }

        try:
            request_data = {"data": json.dumps(
                payload["data"], separators=(',', ':'))}
            response = requests.post(
                url, json=request_data, headers=headers, timeout=30)

            if response.status_code == 200:
                response_data = json.loads(response.text)
                dtp_list = json.loads(response_data["data"]).get("tab", [])

                for dtp in dtp_list:
                    dtp['_gibdd_code'] = code

                all_dtp.extend(dtp_list)
            else:
                logger.error(
                    f"  {city_name} {year}-{month:02d} код {code}: HTTP {response.status_code}")

        except Exception as e:
            logger.error(
                f"  {city_name} {year}-{month:02d} код {code}: {str(e)[:50]}")

        time.sleep(1)

    return all_dtp

# ============================================
# ПОЛУЧЕНИЕ ВСЕХ СТРАНИЦ ЗА МЕСЯЦ
# ============================================


def get_all_dtp_for_month(city_name, year, month):
    all_dtp = []
    page = 1
    page_size = 100

    while True:
        start = (page - 1) * page_size + 1
        end = page * page_size

        dtp = get_dtp_cards(city_name, year, month, start, end)

        if not dtp:
            break

        all_dtp.extend(dtp)

        if len(dtp) < page_size:
            break

        page += 1
        time.sleep(1)

    if all_dtp:
        logger.info(f"  {city_name} {year}-{month:02d}: {len(all_dtp)} ДТП")

    return all_dtp

# ============================================
# СОХРАНЕНИЕ В SUPABASE
# ============================================


def save_dtp_to_supabase(dtp_list, city_name, year, month, region):
    if not dtp_list:
        return 0

    records = []
    for dtp in dtp_list:
        gibdd_code = dtp.get('_gibdd_code')
        kart_id = dtp.get('KartId')

        if not kart_id:
            continue

        records.append({
            "city": city_name,
            "region_id": str(region),
            "district_id": str(gibdd_code),
            "year": str(year),
            "month": str(month).zfill(2),
            "kart_id": str(kart_id),
            "raw_data": json.dumps(dtp, ensure_ascii=False)
        })

    if not records:
        return 0

    saved = 0
    for record in records:
        try:
            existing = supabase.table('gibdd_dtp_buffer')\
                .select('id')\
                .eq('kart_id', record['kart_id'])\
                .eq('district_id', record['district_id'])\
                .execute()

            if not existing.data:
                supabase.table('gibdd_dtp_buffer').insert(record).execute()
                saved += 1
        except:
            pass

    if saved:
        logger.info(
            f"  {city_name} {year}-{month:02d}: сохранено {saved} новых ДТП")

    return saved

# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================


def collect_dtp_for_city(city_name, input_start_year, input_start_month):
    region, codes_list = get_gibdd_codes_for_city(city_name)

    if region is None:
        logger.error(f"{city_name}: нет кодов ГИБДД")
        return 0

    last = supabase.table('gibdd_dtp_buffer')\
        .select('year, month')\
        .eq('city', city_name)\
        .order('year', desc=True)\
        .order('month', desc=True)\
        .limit(1)\
        .execute()

    if last.data:
        start_year = int(last.data[0]['year'])
        start_month = int(last.data[0]['month'])
        logger.info(
            f"{city_name}: данные есть, старт {start_year}-{start_month:02d}")
    else:
        start_year = input_start_year
        start_month = input_start_month
        logger.info(
            f"{city_name}: данных нет, старт {start_year}-{start_month:02d}")

    now = datetime.now()
    total = 0

    for year in range(start_year, now.year + 1):
        if year == start_year and year == now.year:
            months = range(start_month, now.month + 1)
        elif year == start_year:
            months = range(start_month, 13)
        elif year == now.year:
            months = range(1, now.month + 1)
        else:
            months = range(1, 13)

        for month in months:
            dtp_list = get_all_dtp_for_month(city_name, year, month)
            if dtp_list:
                saved = save_dtp_to_supabase(
                    dtp_list, city_name, year, month, region)
                total += saved
            time.sleep(1)

    return total

# ============================================
# ЗАПУСК
# ============================================


if __name__ == "__main__":
    cities = CITIES
    start_year = START_YEAR
    start_month = START_MONTH

    logger.info(
        f"ЗАГРУЗКА ДТП: {cities}, старт {start_year}-{start_month:02d}")

    total = 0
    for city in cities:
        saved = collect_dtp_for_city(city, start_year, start_month)
        total += saved
        logger.info(f"{city}: {saved} ДТП")
        time.sleep(2)

    logger.info(f"ИТОГО: {total} ДТП")
