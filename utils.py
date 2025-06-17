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
    """Извлекает URL из файла regions.json ТОЛЬКО ДЛЯ ЗАСТРОЙЩИКОВ"""
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
        
        # ФИЛЬТР: только застройщики (developer)
        developer_ads = [item for item in ads_data if item.get('author_type') == "developer"]
        
        urls = [item['url'] for item in developer_ads if 'url' in item]
        unique_urls = list(set(urls))  # Убираем дубликаты
        
        with open(codes_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique_urls))
        
        print(f"Извлечено {len(unique_urls)} уникальных URL для застройщиков")
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
        
def extract_domain_from_url(url):
    """Извлекает региональный поддомен из URL"""
    import re
    match = re.search(r'https?://([a-z]+)\.cian\.ru', url)
    return match.group(1) if match else "www"

def extract_block_id_from_data(announcement_id):
    """Извлекает blockId из сохраненных данных объявления"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return None
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем структуру: может быть {"data": [...]} или просто список
        if "data" in data:
            ads_data = data["data"]
        elif isinstance(data, list):
            ads_data = data
        else:
            return None
        
        # Ищем объявление по ID
        for item in ads_data:
            # В данных объявления может быть как строка, так и число. Приводим к строке.
            if 'id' in item and str(item['id']) == str(announcement_id):
                return item.get('blockId')
            # Также проверяем по URL: если в URL есть ID
            if 'url' in item:
                extracted_id = extract_id_from_url(item['url'])
                if extracted_id and extracted_id == str(announcement_id):
                    return item.get('blockId')
        
        return None
    
    except Exception:
        return None

def extract_direct_phone_from_data(announcement_id):
    """Извлекает прямой телефон из сохраненных данных объявления"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return None
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем структуру: может быть {"data": [...]} или просто список
        if "data" in data:
            ads_data = data["data"]
        elif isinstance(data, list):
            ads_data = data
        else:
            return None
        
        # Ищем объявление по ID
        for item in ads_data:
            # В данных объявления может быть как строка, так и число. Приводим к строке.
            if 'id' in item and str(item['id']) == str(announcement_id):
                return item.get('directPhone')
            # Также проверяем по URL: если в URL есть ID
            if 'url' in item:
                extracted_id = extract_id_from_url(item['url'])
                if extracted_id and extracted_id == str(announcement_id):
                    return item.get('directPhone')
        
        return None
    
    except Exception:
        return None

def format_phone(phone):
    """
    Форматирует телефонный номер в стандартный вид: +7 (XXX) XXX-XX-XX
    Если номер не соответствует формату, возвращает оригинал
    """
    if not phone:
        return phone
    
    # Оставляем только цифры
    cleaned = re.sub(r'\D', '', phone)
    
    # Проверяем российские номера
    if cleaned.startswith('8') and len(cleaned) == 11:
        cleaned = '7' + cleaned[1:]
    
    if cleaned.startswith('7') and len(cleaned) == 11:
        return f"+7 ({cleaned[1:4]}) {cleaned[4:7]}-{cleaned[7:9]}-{cleaned[9:11]}"
    
    # Международные номера
    if cleaned.startswith('+') and len(cleaned) > 2:
        return f"+{cleaned[1:]}"
    
    # Неизвестный формат - возвращаем оригинал
    return phone