-- ============================================
-- БУФЕРНЫЕ ТАБЛИЦЫ
-- ============================================

-- Города из Википедии (сырые данные)
CREATE TABLE cities_buffer (
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
);

-- Погода из Open-Meteo (сырые данные)
CREATE TABLE weather_buffer (
    id SERIAL PRIMARY KEY,
    time TEXT,
    city TEXT,
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
);

-- Таблица для регионов (с геометрией)
CREATE TABLE gibdd_regions (
    id SERIAL PRIMARY KEY,
    region_id TEXT NOT NULL,
    region_name TEXT NOT NULL,
    path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица для муниципалитетов (с геометрией и привязкой к региону)
CREATE TABLE gibdd_municipalities (
    id SERIAL PRIMARY KEY,
    gibdd_region_id TEXT,
    region_name TEXT,
    municipality_id TEXT,
    municipality_name TEXT,
    path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_gibdd_municipalities_name ON gibdd_municipalities (municipality_name);

-- Индекс для быстрого поиска по составному ключу (город + регион)
CREATE INDEX idx_gibdd_codes_buffer_city_region ON gibdd_codes_buffer (city, region_name);

CREATE TABLE cities_clean (
    id SERIAL NOT NULL,
    city TEXT NULL,
    region TEXT NULL,
    federal TEXT NULL,
    population INTEGER NULL,
    founded_or_first_mentioned TEXT NULL,
    status TEXT NULL,
    old_names TEXT NULL,
    latitude NUMERIC NULL,
    longitude NUMERIC NULL,
    gibdd_codes TEXT NULL,
    gibdd_region_id TEXT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT NOW(),
    CONSTRAINT cities_clean_pkey PRIMARY KEY (id),
    CONSTRAINT cities_clean_city_region_key UNIQUE (city, region)
);

-- ============================================
-- ЧИСТОВЫЕ ТАБЛИЦЫ (будут создаваться по мере готовности)
-- ============================================

-- weather_clean (позже)
-- gibdd_dtp_main (позже)
-- gibdd_dtp_place (позже)
-- gibdd_vehicles (позже)
-- gibdd_participants_veh (позже)
-- gibdd_participants_other (позже)