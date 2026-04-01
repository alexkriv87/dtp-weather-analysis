# Анализ влияния погоды на ДТП

Проект собирает данные о ДТП (API ГИБДД) и погоде (Open‑Meteo, Яндекс.Геокодер), приводит их к нормальному виду, складывает в PostgreSQL (Supabase) и показывает в дашбордах DataLens.

## Как устроено

- **7 скриптов** — загрузка, очистка, нормализация данных
- **main.py** — запускает всё по порядку
- **config.py** — настройки (города, даты)
- **create_tables.sql** — схема базы данных
- Инкрементальная загрузка — новые данные подтягиваются без дублирования

## Дашборды

- [Сезонность ДТП](https://datalens.ru/66mjf0cghfjkq)
- [Погода и ДТП](https://datalens.ru/kl51lfmtults4)
- [Опасные сочетания погоды](https://datalens.ru/abw84emzm8nwu)

## Технологии

- Python (pandas, requests, python-dotenv)
- PostgreSQL (Supabase)
- DataLens
- Инкрементальная загрузка

## Планирую выполнить

- Переезд на свой PostgreSQL
- Замена ручного парсинга на `pd.json_normalize()`
- Docker и автозапуск

Автор: Алексей Кривошапкин  
GitHub: [alexkriv87](https://github.com/alexkriv87)

## Схема работы

```mermaid
graph LR
    A[API ГИБДД] --> B[Буферные таблицы]
    C[Open-Meteo] --> B
    D[Яндекс.Геокодер] --> B
    B --> E[Нормализация Python]
    E --> F[Чистовые таблицы]
    F --> G[Витрины VIEW]
    G --> H[Дашборды DataLens]

## Схема базы данных

```mermaid
erDiagram
    cities_clean ||--o{ weather_clean : "city_id"
    cities_clean ||--o{ gibdd_dtp_main : "city_id"
    gibdd_dtp_main ||--o{ gibdd_dtp_place : "dtp_id"
    gibdd_dtp_main ||--o{ gibdd_vehicles : "dtp_id"
    gibdd_vehicles ||--o{ gibdd_participants_veh : "vehicle_id"
    gibdd_dtp_main ||--o{ gibdd_participants_other : "dtp_id"

    cities_clean {
        int id PK
        text city
        text region
        int population
        numeric latitude
        numeric longitude
    }

    weather_clean {
        int id PK
        int city_id FK
        timestamp time
        numeric temperature
        numeric precipitation
    }

    gibdd_dtp_main {
        int id PK
        int kart_id
        text district_id
        int city_id FK
        date date
        int fatalities
        int injured
    }

    gibdd_dtp_place {
        int id PK
        int dtp_id FK
        text locality
        text street
        text house
        numeric latitude
        numeric longitude
    }

    gibdd_vehicles {
        int id PK
        int dtp_id FK
        text brand
        text model
        int year
    }

    gibdd_participants_veh {
        int id PK
        int dtp_id FK
        int vehicle_id FK
        text role
        text condition
    }

    gibdd_participants_other {
        int id PK
        int dtp_id FK
        text role
        text condition
    }
