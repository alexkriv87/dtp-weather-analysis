import requests
import pandas as pd
import warnings
from logger_config import setup_logging
import os
from dotenv import load_dotenv
from supabase import create_client, Client

warnings.filterwarnings('ignore')
logger = setup_logging()
load_dotenv()

# ============================================
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ============================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# 1. ПОЛУЧАЕМ ВСЕ ГОРОДА ИЗ БАЗЫ
# ============================================

all_cities = []
start = 0
step = 1000

# Загружаем пачками по 1000 записей (ограничение Supabase)
while True:
    result = supabase.table('cities_buffer')\
        .select('city, region')\
        .range(start, start + step - 1)\
        .execute()

    # Выходим из цикла, когда данные закончились
    if not result.data:
        break

    # Создаем ключ "Город;Регион" для каждого города
    # Это позволяет различать города с одинаковыми названиями из разных регионов
    for record in result.data:
        city_key = f"{record['city']};{record['region']}"
        all_cities.append(city_key)

    start += step

# Создаем множество существующих городов
# Добавляем варианты с "не призн." в названии, так как в Википедии
# есть города с "не призн." в названии
normal_cities = all_cities

ne_cities = []
for city in all_cities:
    city_name, region = city.split(';')
    city_ne = f"{city_name}не призн.;{region}"
    ne_cities.append(city_ne)

existing = set(normal_cities + ne_cities)

logger.info(f"Загружено из базы: {len(all_cities)} городов")

# ============================================
# 2. ПАРСИНГ ВИКИПЕДИИ
# ============================================

params = {
    'action': 'parse',
    'page': 'Список_городов_России',
    'format': 'json',
    'prop': 'text',
    'contentmodel': 'wikitext'
}

headers = {'User-Agent': 'StudentProject/1.0 (alex.kriv87@gmail.com)'}

logger.info("Парсинг Википедии...")
response = requests.get(
    'https://ru.wikipedia.org/w/api.php', params=params, headers=headers)

if response.status_code != 200:
    logger.error(f"Ошибка запроса: {response.status_code}")
    exit()

# Извлекаем таблицу с городами из ответа Википедии
data = response.json()
tables = pd.read_html(data['parse']['text']['*'])
cities_table = tables[0]

# Присваиваем колонкам понятные названия
column_names = ['num', 'sign', 'city', 'region', 'federal',
                'population', 'founded_or_first_mentioned', 'status', 'old_names']

df_wiki = pd.DataFrame(cities_table.values, columns=column_names)
df_wiki = df_wiki.drop(columns=['sign'])

# Добавляем пустые колонки для координат
df_wiki['latitude'] = None
df_wiki['longitude'] = None

# Создаем множество ключей из данных Википедии (без изменений)
wiki_keys = set()
for idx, row in df_wiki.iterrows():
    city_key = f"{row['city']};{row['region']}"
    wiki_keys.add(city_key)

logger.info(f"В Википедии {len(wiki_keys)} городов (с учетом регионов)")

# ============================================
# 3. НАХОДИМ НОВЫЕ ГОРОДА
# ============================================

new_cities_keys = wiki_keys - existing

if not new_cities_keys:
    logger.info("Новых городов нет")
    exit()

logger.info(f"Найдено {len(new_cities_keys)} новых городов")

# ============================================
# 4. ЗАГРУЗКА НОВЫХ ГОРОДОВ В БАЗУ
# ============================================

# Создаем пустой список для хранения данных новых городов
new_cities_list = []

# Перебираем все ключи новых городов (например "Алуштане призн.;Крым")
for key in new_cities_keys:
    # Разделяем ключ на город и регион
    city, region = key.split(';')

    # Ищем в DataFrame Википедии строку, где город и регион совпадают с нашим ключом
    matching_rows = df_wiki[(df_wiki['city'] == city)
                            & (df_wiki['region'] == region)]

    # Если нашли хотя бы одну строку - добавляем её в список
    if len(matching_rows) > 0:
        row = matching_rows.iloc[0].copy()
        new_cities_list.append(row)

# Преобразуем список новых городов в DataFrame
df_new = pd.DataFrame(new_cities_list)

# Теперь чистим названия городов от пометки "не призн."
df_new['city'] = df_new['city'].str.replace('не призн.', '', regex=False)

# Список колонок, которые нужно загрузить в базу данных
columns = ['city', 'region', 'federal', 'population',
           'founded_or_first_mentioned', 'status', 'old_names']

# Перебираем все строки в DataFrame с новыми городами
for idx, row in df_new.iterrows():
    try:
        # Преобразуем строку в словарь, беря только нужные колонки
        city_data = row[columns].to_dict()

        # Заменяем NaN на None (JSON не понимает nan)
        for key, value in city_data.items():
            if pd.isna(value):
                city_data[key] = None

        # Добавляем пустые поля для координат
        city_data['latitude'] = None
        city_data['longitude'] = None

        # Вставляем данные в таблицу cities_buffer
        result = supabase.table('cities_buffer').insert(city_data).execute()

        # Проверяем результат вставки
        if result.data:
            logger.info(f"Город {row['city']} ({row['region']}) сохранен")
        else:
            logger.error(f"Город {row['city']} не сохранен")

    except Exception as e:
        logger.error(f"Город {row['city']}: {e}")

# Итоговое сообщение о количестве загруженных городов
logger.info(f"Загрузка завершена. Добавлено {len(df_new)} новых городов")

# Сохраняем резервную копию всех данных из Википедии
df_wiki.to_csv('cities_backup.csv', index=False, encoding='utf-8-sig', sep=';')
