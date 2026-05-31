# main.py

import subprocess
import time
from notifier import send_email
from config import CITIES

start_time = time.time()


scripts = [
    '01_EL_cities_from_wiki.py',
    '02_EL_geocode_cities.py',
    # '03_EL_gibdd_codes.py',
    '04_T_cities_clean.py',
    '05_EL_weather_openmeteo.py',
    '06_EL_gibdd_dtp.py',
    '07_T_weather_clean.py',
    '08_T_gibdd_normalize.py',
]

for script in scripts:
    print(f'Запуск {script}...')
    result = subprocess.run(['python', script])
    if result.returncode != 0:
        send_email(
            "❌ ОШИБКА в ETL пайплайне",
            f"Скрипт {script} завершился с ошибкой (код {result.returncode})\nВремя: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        exit(1)
    time.sleep(2)
    print(f'Завершен {script}\n')

total_sec = time.time() - start_time
total_min = int(total_sec // 60)
total_sec_rem = int(total_sec % 60)

# Отправляем уведомление об успешном завершении
send_email(
    "✅ ETL пайплайн завершён",
    f"Города: {', '.join(CITIES)}\nОбщее время: {total_min} мин {total_sec_rem} сек\nВремя завершения: {time.strftime('%Y-%m-%d %H:%M:%S')}"
)

print(
    f"\n✅ Общее время: {int(total_sec // 3600)} ч {int((total_sec % 3600) // 60)} мин {int(total_sec % 60)} сек")
