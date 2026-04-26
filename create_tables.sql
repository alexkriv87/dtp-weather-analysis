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
);

CREATE INDEX idx_weather_buffer_city_time ON weather_buffer (city, time);
CREATE INDEX idx_weather_buffer_city_id ON weather_buffer (city_id);

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

CREATE TABLE gibdd_dtp_buffer (
    id SERIAL PRIMARY KEY,
    city TEXT,
    city_id INTEGER,              
    district_id TEXT,
    gibdd_region_id TEXT,         
    date TEXT,
    kart_id TEXT,
    raw_data TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_gibdd_dtp_buffer_city_date ON gibdd_dtp_buffer (city, date);
CREATE UNIQUE INDEX idx_gibdd_dtp_buffer_kart_id ON gibdd_dtp_buffer (kart_id, district_id);

-- ============================================
-- ЧИСТОВЫЕ ТАБЛИЦЫ
-- ============================================

-- Нормализованные города
CREATE TABLE weather_clean (
    id SERIAL PRIMARY KEY,
    city_id INTEGER NOT NULL,
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    time_local TIMESTAMP WITH TIME ZONE,
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(city_id, time)
);

CREATE INDEX idx_weather_clean_city_time ON weather_clean (city_id, time);


-- gibdd_dtp_main (позже)
-- gibdd_dtp_place (позже)
-- gibdd_vehicles (позже)
-- gibdd_participants_veh (позже)
-- gibdd_participants_other (позже)