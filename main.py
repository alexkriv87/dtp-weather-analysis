import subprocess
import time

scripts = [
    '01_EL_cities_from_wiki.py',
    '02_EL_geocode_cities.py',
    '03_EL_weather_openmeteo.py',
    '04_EL_gibdd_dtp.py',
    '05_T_cities_clean.py',
    '06_T_weather_clean.py',
    '07_T_gibdd_normalize.py'
]

for script in scripts:
    print(f'Запуск {script}...')
    subprocess.run(['python', script])
    time.sleep(2)
    print(f'Завершен {script}\n')