# create_all_tables.py
"""
Гибкий скрипт для создания таблиц на Timeweb.
Можно закомментировать ненужные секции.
"""

from db import execute_sql
from logger_config import setup_logging

logger = setup_logging()

# ============================================
# 1. БУФЕРНЫЕ ТАБЛИЦЫ
# ============================================


def create_cities_buffer():
    logger.info("Создаём cities_buffer...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS cities_buffer (
            id SERIAL PRIMARY KEY,
            city TEXT,
            region TEXT,
            federal TEXT,
            population TEXT,
            founded_or_first_mentioned TEXT,
            status TEXT,
            old_names TEXT,
            latitude TEXT,
            longitude TEXT,
            gibdd_codes TEXT,
            gibdd_region_id TEXT,
            gibdd_type TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


def create_weather_buffer():
    logger.info("Создаём weather_buffer...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS weather_buffer (
            id SERIAL PRIMARY KEY,
            time TEXT,
            city TEXT,
            city_id INTEGER,
            temperature_2m TEXT,
            soil_temperature_0cm TEXT,
            apparent_temperature TEXT,
            precipitation TEXT,
            rain TEXT,
            snowfall TEXT,
            snow_depth TEXT,
            wind_speed_10m TEXT,
            wind_gusts_10m TEXT,
            wind_direction_10m TEXT,
            visibility TEXT,
            cloud_cover TEXT,
            is_day TEXT,
            weather_code TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_weather_buffer_city_time ON weather_buffer (city, time)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_weather_buffer_city_id ON weather_buffer (city_id)")


def create_gibdd_regions():
    logger.info("Создаём gibdd_regions...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_regions (
            id SERIAL PRIMARY KEY,
            region_id TEXT NOT NULL,
            region_name TEXT NOT NULL,
            path TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


def create_gibdd_municipalities():
    logger.info("Создаём gibdd_municipalities...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_municipalities (
            id SERIAL PRIMARY KEY,
            gibdd_region_id TEXT,
            region_name TEXT,
            municipality_id TEXT,
            municipality_name TEXT,
            path TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_municipalities_name ON gibdd_municipalities (municipality_name)")


def create_gibdd_dtp_buffer():
    logger.info("Создаём gibdd_dtp_buffer...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_dtp_buffer (
            id BIGSERIAL PRIMARY KEY,
            kart_id TEXT NOT NULL,
            district_id TEXT NOT NULL,
            city TEXT,
            city_id INTEGER,
            region_id TEXT,
            gibdd_region_id TEXT,
            year TEXT,
            month TEXT,
            date TEXT,
            raw_data TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(kart_id, district_id)
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_city ON gibdd_dtp_buffer(city)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_city_id ON gibdd_dtp_buffer(city_id)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_kart_id ON gibdd_dtp_buffer(kart_id)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_date ON gibdd_dtp_buffer(date)")

# ============================================
# 2. ЧИСТОВЫЕ ТАБЛИЦЫ (погода и города)
# ============================================


def create_cities_clean():
    logger.info("Создаём cities_clean...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS cities_clean (
            id SERIAL PRIMARY KEY,
            city TEXT,
            region TEXT,
            federal TEXT,
            population INTEGER,
            founded_or_first_mentioned TEXT,
            status TEXT,
            old_names TEXT,
            latitude NUMERIC,
            longitude NUMERIC,
            gibdd_codes TEXT,
            gibdd_region_id TEXT,
            gibdd_type TEXT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(city, region)
        )
    """)


def create_weather_clean():
    logger.info("Создаём weather_clean...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS weather_clean (
            id SERIAL PRIMARY KEY,
            city_id INTEGER NOT NULL,
            time_utc TIMESTAMP NOT NULL,
            time_local TIMESTAMP,
            temperature NUMERIC,
            apparent_temperature NUMERIC,
            precipitation NUMERIC,
            rain NUMERIC,
            snowfall NUMERIC,
            snow_depth NUMERIC,
            wind_speed_10m NUMERIC,
            wind_gusts_10m NUMERIC,
            wind_direction_10m NUMERIC,
            cloud_cover NUMERIC,
            is_day NUMERIC,
            weather_code NUMERIC,
            visibility NUMERIC,
            soil_temperature_0cm NUMERIC,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(city_id, time_utc)
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_weather_clean_city_time ON weather_clean (city_id, time_utc)")

# ============================================
# 3. ЧИСТОВЫЕ ТАБЛИЦЫ ДТП (5 таблиц)
# ============================================


def create_gibdd_dtp_main():
    logger.info("Создаём gibdd_dtp_main...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_dtp_main (
            id SERIAL PRIMARY KEY,
            buffer_id INTEGER,
            kart_id BIGINT NOT NULL,
            district_id TEXT NOT NULL,
            city_id INTEGER,
            date DATE,
            time TIME,
            dtp_type TEXT,
            fatalities INTEGER DEFAULT 0,
            injured INTEGER DEFAULT 0,
            vehicles_count INTEGER DEFAULT 0,
            participants_count INTEGER DEFAULT 0,
            emtp_number TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(kart_id, district_id)
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_main_kart_id ON gibdd_dtp_main(kart_id)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_main_date ON gibdd_dtp_main(date)")
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_main_city_id ON gibdd_dtp_main(city_id)")


def create_gibdd_dtp_place():
    logger.info("Создаём gibdd_dtp_place...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_dtp_place (
            id SERIAL PRIMARY KEY,
            dtp_id INTEGER NOT NULL REFERENCES gibdd_dtp_main(id) ON DELETE CASCADE,
            locality TEXT,
            street TEXT,
            house TEXT,
            road_category TEXT,
            weather TEXT[],
            road_condition TEXT,
            light TEXT,
            latitude NUMERIC,
            longitude NUMERIC,
            road_disadvantages TEXT[],
            location_scheme TEXT[],
            nearby_objects TEXT[]
        )
    """)


def create_gibdd_vehicles():
    logger.info("Создаём gibdd_vehicles...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_vehicles (
            id SERIAL PRIMARY KEY,
            dtp_id INTEGER NOT NULL REFERENCES gibdd_dtp_main(id) ON DELETE CASCADE,
            vehicle_number TEXT,
            vehicle_status TEXT,
            vehicle_type TEXT,
            brand TEXT,
            model TEXT,
            color TEXT,
            drive_type TEXT,
            year INTEGER,
            has_trailer TEXT,
            tech_condition TEXT,
            ownership TEXT,
            owner_type TEXT
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_vehicles_dtp_id ON gibdd_vehicles(dtp_id)")


def create_gibdd_participants_veh():
    logger.info("Создаём gibdd_participants_veh...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_participants_veh (
            id SERIAL PRIMARY KEY,
            dtp_id INTEGER NOT NULL REFERENCES gibdd_dtp_main(id) ON DELETE CASCADE,
            vehicle_id INTEGER REFERENCES gibdd_vehicles(id) ON DELETE CASCADE,
            role TEXT,
            condition TEXT,
            gender TEXT,
            driving_experience INTEGER,
            alcohol TEXT,
            seat_belt TEXT,
            leaving TEXT,
            participant_number TEXT,
            seat_group TEXT,
            injured_card_id TEXT,
            violations TEXT[],
            other_violations TEXT[]
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_participants_veh_dtp_id ON gibdd_participants_veh(dtp_id)")


def create_gibdd_participants_other():
    logger.info("Создаём gibdd_participants_other...")
    execute_sql("""
        CREATE TABLE IF NOT EXISTS gibdd_participants_other (
            id SERIAL PRIMARY KEY,
            dtp_id INTEGER NOT NULL REFERENCES gibdd_dtp_main(id) ON DELETE CASCADE,
            role TEXT,
            condition TEXT,
            gender TEXT,
            alcohol TEXT,
            leaving TEXT,
            participant_number TEXT,
            violations TEXT[],
            other_violations TEXT[]
        )
    """)
    execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_gibdd_participants_other_dtp_id ON gibdd_participants_other(dtp_id)")


# ============================================
# MAIN — ЗДЕСЬ ВЫБИРАЕШЬ, ЧТО СОЗДАВАТЬ
# ============================================

def main():
    logger.info("=" * 60)
    logger.info("СОЗДАНИЕ ТАБЛИЦ НА TIMEWEB")
    logger.info("=" * 60)

    # ЗАКОММЕНТИРУЙ ТО, ЧТО НЕ НУЖНО
    # ============================================
    # 1. Буферные таблицы
    # ============================================
    create_cities_buffer()
    create_weather_buffer()
    create_gibdd_regions()
    create_gibdd_municipalities()
    create_gibdd_dtp_buffer()

    # ============================================
    # 2. Чистовые (погода, города)
    # ============================================
    create_cities_clean()
    create_weather_clean()

    # ============================================
    # 3. Чистовые ДТП (5 таблиц)
    # ============================================
    create_gibdd_dtp_main()
    create_gibdd_dtp_place()
    create_gibdd_vehicles()
    create_gibdd_participants_veh()
    create_gibdd_participants_other()

    logger.info("=" * 60)
    logger.info("ГОТОВО ✅")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Ошибка: {e}")
        import traceback
        logger.critical(traceback.format_exc())
