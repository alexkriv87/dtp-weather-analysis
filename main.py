import subprocess
import time

start_time = time.time()

scripts = [
    '01_EL_cities_from_wiki.py',
    '02_EL_geocode_cities.py',
    '03_EL_gibdd_codes.py',
    '04_T_cities_clean.py',
    '05_EL_weather_openmeteo.py',
    '06_EL_gibdd_dtp.py',
    '07_T_weather_clean.py',
    # '08_T_gibdd_normalize.py',  # временно отключён
]

for script in scripts:
    print(f'Запуск {script}...')
    subprocess.run(['python', script])
    time.sleep(2)
    print(f'Завершен {script}\n')

total_sec = time.time() - start_time
print(
    f"\n✅ Общее время: {int(total_sec // 3600)} ч {int((total_sec % 3600) // 60)} мин {int(total_sec % 60)} сек")
