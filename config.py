# config.py

import argparse


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", type=str, help="Города через запятую")
    parser.add_argument("--start-year", type=int,
                        help="Год начала (например, 2021)")
    parser.add_argument("--start-month", type=int, help="Месяц начала (1-12)")
    args, unknown = parser.parse_known_args()
    return args


# Значения по умолчанию
DEFAULT_CITIES = ["Балашиха"]
DEFAULT_START_YEAR = 2025
DEFAULT_START_MONTH = 12

args = parse_args()

CITIES = args.cities.split(',') if args.cities else DEFAULT_CITIES
START_YEAR = args.start_year if args.start_year else DEFAULT_START_YEAR
START_MONTH = args.start_month if args.start_month else DEFAULT_START_MONTH
