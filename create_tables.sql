-- ============================================
-- БУФЕРНЫЕ ТАБЛИЦЫ (сырые данные из API)
-- ============================================

-- Города из Википедии (сырые данные)
CREATE TABLE cities_buffer (
    id SERIAL PRIMARY KEY,
    city TEXT,                              -- Название города
    region TEXT,                            -- Регион
    federal TEXT,                           -- Федеральный округ
    population TEXT,                        -- Население (текст, т.к. есть пробелы)
    founded_or_first_mentioned TEXT,        -- Дата основания или первого упоминания
    status TEXT,                            -- Статус города
    old_names TEXT,                         -- Старые названия
    latitude TEXT,                          -- Широта (текст, т.к. парсим из Википедии)
    longitude TEXT,                         -- Долгота
    gibdd_codes TEXT,                       -- Коды ГИБДД для районов города
    gibdd_region_id TEXT,                   -- ID региона в системе ГИБДД
    gibdd_type TEXT,                        -- Тип региона (город/район)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Погода из Open-Meteo (сырые данные)
CREATE TABLE weather_buffer (
    id SERIAL PRIMARY KEY,
    time TEXT,                              -- Время UTC (строка, потом преобразуем)
    city TEXT,                              -- Название города
    city_id INTEGER,                        -- ID города из cities_clean
    temperature_2m TEXT,                    -- Температура на высоте 2м
    soil_temperature_0cm TEXT,              -- Температура почвы
    apparent_temperature TEXT,              -- Ощущаемая температура
    precipitation TEXT,                     -- Осадки общие
    rain TEXT,                              -- Дождь
    snowfall TEXT,                          -- Снег
    snow_depth TEXT,                        -- Глубина снега
    wind_speed_10m TEXT,                    -- Скорость ветра на высоте 10м
    wind_gusts_10m TEXT,                    -- Порывы ветра
    wind_direction_10m TEXT,                -- Направление ветра
    visibility TEXT,                        -- Видимость
    cloud_cover TEXT,                       -- Облачность
    is_day TEXT,                            -- День/ночь (1/0)
    weather_code TEXT,                      -- Код погоды WMO
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для быстрого поиска по погоде
CREATE INDEX idx_weather_buffer_city_time ON weather_buffer (city, time);
CREATE INDEX idx_weather_buffer_city_id ON weather_buffer (city_id);

-- Регионы ГИБДД (справочник с геометрией)
CREATE TABLE gibdd_regions (
    id SERIAL PRIMARY KEY,
    region_id TEXT NOT NULL,                -- ID региона в системе ГИБДД
    region_name TEXT NOT NULL,              -- Название региона
    path TEXT,                              -- GeoJSON путь (для карт)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Муниципалитеты ГИБДД (районы и города с геометрией)
CREATE TABLE gibdd_municipalities (
    id SERIAL PRIMARY KEY,
    gibdd_region_id TEXT,                   -- ID родительского региона
    region_name TEXT,                       -- Название региона
    municipality_id TEXT,                   -- ID муниципалитета в системе ГИБДД
    municipality_name TEXT,                 -- Название муниципалитета
    path TEXT,                              -- GeoJSON путь
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_gibdd_municipalities_name ON gibdd_municipalities (municipality_name);

-- Буфер ДТП (сырые JSON от API ГИБДД) — с city_id, gibdd_region_id и date
CREATE TABLE IF NOT EXISTS gibdd_dtp_buffer (
    id BIGSERIAL PRIMARY KEY,
    kart_id TEXT NOT NULL,                  -- Уникальный номер ДТП в системе ГИБДД
    district_id TEXT NOT NULL,              -- ID района/муниципалитета
    city TEXT,                              -- Название города
    city_id INTEGER,                        -- ID города из cities_clean
    region_id TEXT,                         -- ID региона (из API)
    gibdd_region_id TEXT,                   -- ID региона из cities_clean (для связи)
    year TEXT,                              -- Год ДТП
    month TEXT,                             -- Месяц ДТП
    date TEXT,                              -- Дата ДТП в формате ГГГГ-ММ-01 (для группировки)
    raw_data TEXT,                          -- Сырой JSON ответа API
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(kart_id, district_id)            -- Уникальность по паре ключей
);

-- Индексы для буфера ДТП
CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_city ON gibdd_dtp_buffer(city);
CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_city_id ON gibdd_dtp_buffer(city_id);
CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_kart_id ON gibdd_dtp_buffer(kart_id);
CREATE INDEX IF NOT EXISTS idx_gibdd_dtp_buffer_date ON gibdd_dtp_buffer(date);

-- ============================================
-- ЧИСТОВЫЕ ТАБЛИЦЫ (нормализованные данные)
-- ============================================

-- Погода очищенная (числовые значения, привязка к city_id)
CREATE TABLE weather_clean (
    id SERIAL PRIMARY KEY,
    city_id INTEGER NOT NULL,               -- Ссылка на cities_clean.id
    time_utc TIMESTAMP NOT NULL,            -- Время в UTC
    time_local TIMESTAMP,                   -- Время в локальном поясе города
    temperature NUMERIC,                    -- Температура (число)
    apparent_temperature NUMERIC,           -- Ощущаемая температура
    precipitation NUMERIC,                  -- Осадки
    rain NUMERIC,                           -- Дождь
    snowfall NUMERIC,                       -- Снег
    snow_depth NUMERIC,                     -- Глубина снега
    wind_speed_10m NUMERIC,                 -- Скорость ветра
    wind_gusts_10m NUMERIC,                 -- Порывы ветра
    wind_direction_10m NUMERIC,             -- Направление ветра
    cloud_cover NUMERIC,                    -- Облачность
    is_day NUMERIC,                         -- День (1) / Ночь (0)
    weather_code NUMERIC,                   -- Код погоды WMO
    visibility NUMERIC,                     -- Видимость
    soil_temperature_0cm NUMERIC,           -- Температура почвы
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(city_id, time_utc)               -- Одна погода на город+время
);

CREATE INDEX idx_weather_clean_city_time ON weather_clean (city_id, time_utc);

-- ============================================
-- ПРИМЕЧАНИЯ ПО НЕДОСТАЮЩИМ ТАБЛИЦАМ
-- ============================================

-- Остальные чистовые таблицы (gibdd_dtp_main, gibdd_dtp_place,
-- gibdd_vehicles, gibdd_participants_veh, gibdd_participants_other)
-- будут созданы отдельным скриптом (create_dtp_tables_timeweb.sql)