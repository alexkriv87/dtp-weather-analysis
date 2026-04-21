

"""
Модуль для загрузки городов из Википедии в таблицу cities_buffer.

1. Парсит страницу «Список городов России».
2. Загружает из БД уже существующие города.
3. Находит новые города (которых ещё нет в БД).
4. Добавляет новые города в cities_buffer одной вставкой.
"""

import requests
import pandas as pd
import warnings
from logger_config import setup_logging
from db import read_sql, df_to_sql

warnings.filterwarnings('ignore')
logger = setup_logging()

# ============================================
# 1. ЗАГРУЖАЕМ СУЩЕСТВУЮЩИЕ ГОРОДА ИЗ БД
# ============================================

logger.info("Загружаем существующие города из БД")
df_existing = read_sql("SELECT city, region FROM cities_buffer")

existing_keys = set()
for _, row in df_existing.iterrows():
    city_key = f"{row['city']};{row['region']}"
    existing_keys.add(city_key)

# Добавляем варианты с "не призн." (для городов из Википедии с такой пометкой)
ne_cities = []
for key in existing_keys:
    city_name, region = key.split(';')
    city_ne = f"{city_name}не призн.;{region}"
    ne_cities.append(city_ne)

existing_keys.update(ne_cities)

logger.info(f"Загружено из БД: {len(df_existing)} городов")

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

data = response.json()
tables = pd.read_html(data['parse']['text']['*'])
cities_table = tables[0]

# Приводим таблицу к нужному формату
column_names = ['num', 'sign', 'city', 'region', 'federal',
                'population', 'founded_or_first_mentioned', 'status', 'old_names']
df_wiki = pd.DataFrame(cities_table.values, columns=column_names)
df_wiki = df_wiki.drop(columns=['sign'])

# Создаём множество ключей из Википедии (город;регион)
wiki_keys = set()
for _, row in df_wiki.iterrows():
    city_key = f"{row['city']};{row['region']}"
    wiki_keys.add(city_key)

logger.info(f"В Википедии {len(wiki_keys)} городов (с учётом регионов)")

# ============================================
# 3. НАХОДИМ НОВЫЕ ГОРОДА
# ============================================

new_cities_keys = wiki_keys - existing_keys

if not new_cities_keys:
    logger.info("Новых городов нет")
    exit()

logger.info(f"Найдено {len(new_cities_keys)} новых городов")

# ============================================
# 4. ПОДГОТОВКА DATAFRAME ДЛЯ ВСТАВКИ
# ============================================

new_cities_list = []
for key in new_cities_keys:
    city, region = key.split(';')
    matching_rows = df_wiki[(df_wiki['city'] == city)
                            & (df_wiki['region'] == region)]
    if len(matching_rows) > 0:
        row = matching_rows.iloc[0].copy()
        new_cities_list.append(row)

df_new = pd.DataFrame(new_cities_list)

# Очищаем названия от пометки "не призн."
df_new['city'] = df_new['city'].str.replace('не призн.', '', regex=False)

# Оставляем только нужные колонки (порядок как в таблице cities_buffer)
columns_to_insert = ['city', 'region', 'federal', 'population',
                     'founded_or_first_mentioned', 'status', 'old_names']
df_to_insert = df_new[columns_to_insert].copy()
df_to_insert['latitude'] = None
df_to_insert['longitude'] = None

# ============================================
# 5. ВСТАВКА НОВЫХ ГОРОДОВ В БД
# ============================================

try:
    df_to_sql(df_to_insert, 'cities_buffer', if_exists='append')
    logger.info(f"Успешно добавлено {len(df_to_insert)} новых городов")
except Exception as e:
    logger.error(f"Ошибка при вставке городов: {e}")
