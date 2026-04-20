import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pandas as pd

load_dotenv()  # Загружаем переменные из .env

# ============================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ
# ============================================

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)


def get_engine():
    """Возвращает объект подключения к БД"""
    return engine

# ============================================
# ЗАГРУЗКА ДАННЫХ ИЗ DATAFRAME В ТАБЛИЦУ
# ============================================


def df_to_sql(df, table_name, if_exists='append', chunksize=None):
    """
    Загружает DataFrame в таблицу БД.
    Параметры:
        df - DataFrame
        table_name - имя таблицы
        if_exists - 'append' (добавить), 'replace' (пересоздать), 'fail' (ошибка)
        chunksize - количество строк в одной пачке (None = все сразу)
    Возвращает количество вставленных строк.
    """
    with engine.connect() as conn:
        df.to_sql(table_name, conn, if_exists=if_exists,
                  index=False, chunksize=chunksize)
    return len(df)

# ============================================
# ВСТАВКА ДАННЫХ ЧЕРЕЗ executemany
# ============================================


def insert_many(query, data):
    """
    Выполняет пакетную вставку данных.
    Параметры:
        query - SQL-запрос с плейсхолдерами (%s)
        data - список кортежей (каждый кортеж — одна строка)
    Возвращает количество вставленных строк.
    """
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text(query), data)
    return len(data)

# ============================================
# ЧТЕНИЕ SQL-ЗАПРОСА В DATAFRAME
# ============================================


def read_sql(query):
    """Выполняет SQL-запрос и возвращает результат в виде DataFrame"""
    return pd.read_sql(query, engine)

# ============================================
# ВЫПОЛНЕНИЕ ПРОИЗВОЛЬНОГО SQL-ЗАПРОСА
# ============================================


def execute_sql(query):
    """Выполняет SQL-запрос (например, DELETE, UPDATE)"""
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text(query))
