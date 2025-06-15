import os
import json
import re
import time
from datetime import datetime

def ensure_output_dir():
    """Создает директорию output если ее нет"""
    os.makedirs("output", exist_ok=True)

def get_region_file():
    """Возвращает путь к файлу с объявлениями"""
    return "output/regions.json"

def get_codes_file():
    """Возвращает путь к файлу с URL"""
    return "output/codes.txt"

def get_phones_file():
    """Возвращает путь к файлу с телефонами"""
    return "output/data.json"

def extract_id_from_url(url):
    """Извлекает ID объявления из URL"""
    clean_url = url.strip().replace('"', '').replace("'", "")
    
    # Проверяем несколько возможных паттернов
    patterns = [
        r'/(\d+)/?$',            # Стандартный формат
        r'flat/(\d+)[/?]',        # С параметрами
        r'cian\.ru/sale/flat/(\d+)' # Разные варианты
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_url)
        if match:
            return match.group(1)
    
    print(f"Не удалось извлечь ID из URL: {clean_url}")
    return None

def extract_urls_from_regions():
    """Извлекает URL из файла regions.json"""
    region_file = get_region_file()
    codes_file = get_codes_file()
    
    if not os.path.exists(region_file):
        print(f"Файл {region_file} не найден!")
        return []
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем разные возможные структуры
        if "data" in data and isinstance(data["data"], list):
            ads_data = data["data"]
        elif isinstance(data, list):
            ads_data = data
        else:
            print("Неверный формат файла regions.json")
            return []
        
        urls = [item['url'] for item in ads_data if 'url' in item]
        unique_urls = list(set(urls))  # Убираем дубликаты
        
        with open(codes_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique_urls))
        
        print(f"Извлечено {len(unique_urls)} уникальных URL")
        return unique_urls
    
    except Exception as e:
        print(f"Ошибка при извлечении URL: {str(e)}")
        return []

def is_parsing_in_progress():
    """Проверяет, запущен ли уже процесс парсинга"""
    lock_file = "output/parsing.lock"
    # Проверяем наличие lock-файла
    if os.path.exists(lock_file):
        # Проверяем, когда был создан файл
        file_time = os.path.getmtime(lock_file)
        # Если файл старше 1 часа - считаем что процесс завис
        if time.time() - file_time > 3600:
            return False
        return True
    return False

def start_parsing():
    """Создает lock-файл для отслеживания процесса"""
    with open("output/parsing.lock", 'w') as f:
        f.write(str(datetime.now()))

def finish_parsing():
    """Удаляет lock-файл после завершения"""
    lock_file = "output/parsing.lock"
    if os.path.exists(lock_file):
        os.remove(lock_file)