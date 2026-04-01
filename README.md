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
