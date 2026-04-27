# 06_EL_gibdd_dtp.py
"""
Модуль для загрузки данных о ДТП из API ГИБДД.

1. Получает коды ГИБДД и city_id для города из cities_clean.
2. Определяет недостающие месяцы (которых нет в gibdd_dtp_buffer).
3. Для каждого недостающего месяца загружает ДТП через API (с пагинацией).
4. Сохраняет данные в gibdd_dtp_buffer.
"""

import requests
import json
import time
import sys
import pandas as pd
from datetime import datetime
from logger_config import setup_logging
from db import read_sql, df_to_sql, get_engine
from config import CITIES, START_DATE

logger = setup_logging()
engine = get_engine()


# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def get_gibdd_codes(city_name):
    """
    Получает коды ГИБДД и city_id для города из таблицы cities_clean.
    Возвращает (city_id, region_id, список district_codes) или (None, None, None).
    """
    query = f"""
        SELECT id, gibdd_region_id, gibdd_codes
        FROM cities_clean
        WHERE city = '{city_name}'
    """
    df = read_sql(query)
    if df.empty:
        return None, None, None
    city_id = df.iloc[0]['id']
    region_id = df.iloc[0]['gibdd_region_id']
    codes_str = df.iloc[0]['gibdd_codes']
    if not region_id or not codes_str:
        return city_id, None, None
    return city_id, region_id, codes_str.split(',')


def get_existing_months(city_name):
    """
    Возвращает множество месяцев (YYYY-MM), которые уже есть в gibdd_dtp_buffer для города.
    """
    query = f"""
        SELECT DISTINCT date
        FROM gibdd_dtp_buffer
        WHERE city = '{city_name}'
    """
    df = read_sql(query)
    if df.empty:
        return set()
    # Извлекаем год и месяц из полной даты
    return set(pd.to_datetime(df['date']).dt.strftime('%Y-%m'))


def generate_all_months(start_date):
    """
    Генерирует все месяцы от start_date до текущего месяца.
    Возвращает множество строк в формате YYYY-MM.
    """
    months = set()
    current = datetime.strptime(start_date, '%Y-%m-%d')
    # Переводим на первый день месяца
    current = current.replace(day=1)
    now = datetime.now().replace(day=1)

    while current <= now:
        months.add(current.strftime('%Y-%m'))
        # переходим к следующему месяцу
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def fetch_dtp_for_month(city_name, city_id, region_id, district_codes, year, month):
    """
    Загружает ДТП за конкретный месяц через API ГИБДД.
    Возвращает список записей (словарей) или пустой список при ошибке.
    """
    url = "http://stat.gibdd.ru/map/getDTPCardData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    all_records = []
    page_size = 100
    page = 1

    for code in district_codes:
        while True:
            start = (page - 1) * page_size + 1
            end = page * page_size

            payload = {
                "data": {
                    "date": [f"MONTHS:{month}.{year}"],
                    "ParReg": region_id,
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

                if response.status_code != 200:
                    logger.error(f"  HTTP {response.status_code} для {code}")
                    break

                response_data = response.json()
                dtp_list = json.loads(response_data["data"]).get("tab", [])

                if not dtp_list:
                    break

                for dtp in dtp_list:
                    # Сохраняем сырой JSON
                    raw_json = json.dumps(dtp, ensure_ascii=False)

                    # Создаём запись для БД
                    record = {
                        'city': city_name,
                        'city_id': city_id,
                        'district_id': code,
                        'region_id': region_id,
                        'gibdd_region_id': region_id,
                        'year': str(year),
                        'month': str(month),
                        'date': f"{year}-{month:02d}-01",
                        'kart_id': dtp.get('KartId'),
                        'raw_data': raw_json
                    }
                    all_records.append(record)

                if len(dtp_list) < page_size:
                    break

                page += 1
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"  Ошибка при запросе для {code}: {str(e)[:50]}")
                break

        time.sleep(1)

    if all_records:
        logger.info(
            f"    Загружено {len(all_records)} ДТП за {year}-{month:02d}")
    return all_records


def save_dtp_data(records, city_name):
    """
    Сохраняет записи в gibdd_dtp_buffer через df_to_sql пачками по 500 строк.
    Возвращает количество сохранённых записей.
    """
    if not records:
        return 0

    df = pd.DataFrame(records)

    # Преобразуем kart_id в строку (если есть)
    if 'kart_id' in df.columns:
        df['kart_id'] = df['kart_id'].astype(str)

    # Выбираем нужные колонки
    columns_to_insert = [
        'city', 'city_id', 'district_id',
        'region_id', 'gibdd_region_id',
        'year', 'month', 'date', 'kart_id', 'raw_data'
    ]
    df_to_insert = df[columns_to_insert].copy()

    try:
        df_to_sql(df_to_insert, 'gibdd_dtp_buffer',
                  if_exists='append', chunksize=500)
        logger.info(f"    Сохранено {len(df_to_insert)} записей")
        return len(df_to_insert)
    except Exception as e:
        logger.error(f"  Ошибка при сохранении в БД: {e}")
        return 0


# ============================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================

def main():
    logger.info("=" * 60)
    logger.info("ЗАГРУЗКА ДАННЫХ О ДТП ИЗ API ГИБДД")
    logger.info("=" * 60)

    for city_name in CITIES:
        logger.info(f"\nОбработка города: {city_name}")

        # Получаем коды ГИБДД и city_id для города
        city_id, region_id, district_codes = get_gibdd_codes(city_name)
        if city_id is None:
            logger.warning(f"  Город не найден в cities_clean")
            continue
        if region_id is None:
            logger.warning(f"  Коды ГИБДД не найдены для города {city_name}")
            continue

        logger.info(
            f"  city_id: {city_id}, код региона: {region_id}, кодов районов: {len(district_codes)}")

        # Получаем множество уже загруженных месяцев
        existing_months = get_existing_months(city_name)
        logger.info(f"  Уже загружено месяцев: {len(existing_months)}")

        # Генерируем все месяцы от START_DATE до текущего
        all_months = generate_all_months(START_DATE)
        missing_months = all_months - existing_months

        if not missing_months:
            logger.info("  Все месяцы уже загружены")
            continue

        logger.info(f"  Недостающих месяцев: {len(missing_months)}")

        # Сортируем недостающие месяцы
        missing_list = sorted(missing_months)

        total_saved = 0
        for month_str in missing_list:
            year, month = map(int, month_str.split('-'))
            logger.info(f"  Загружаем месяц: {year}-{month:02d}")

            records = fetch_dtp_for_month(
                city_name, city_id, region_id, district_codes, year, month)
            if records:
                saved = save_dtp_data(records, city_name)
                total_saved += saved

            time.sleep(2)  # пауза между месяцами

        logger.info(
            f"  Всего сохранено для {city_name}: {total_saved} записей")

    logger.info("\n" + "=" * 60)
    logger.info("ЗАГРУЗКА ДТП ЗАВЕРШЕНА")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        sys.exit(1)
