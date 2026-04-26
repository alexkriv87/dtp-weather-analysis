# logger_config.py

import logging


def setup_logging() -> logging.Logger:
    '''Настройка логирования.'''

    # Название файла логов (можно использовать несколько файлов, если скрипт большой)
    log_filename = f'common.log'

    logger = logging.getLogger('dtp_weather')  # Название логера
    logger.setLevel(logging.INFO)

    # Очистка существующих обработчиков
    if logger.handlers:
        logger.handlers.clear()

    # Обработчик для файла
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    # Формат вывода сообщений логов в файл
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    # Формат вывода логов в консоль (сокращенный)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger
