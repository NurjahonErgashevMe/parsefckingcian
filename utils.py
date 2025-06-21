import os
import re
import json
import sqlite3
from urllib.parse import urlparse
from datetime import datetime
from contextlib import closing
from database import init_db

DB_NAME = "cian_bot.db"

def ensure_output_dir():
    """Создает папку output если её нет"""
    os.makedirs("output", exist_ok=True)

def clear_parsing_data():
    """Удаляет все файлы с данными парсинга"""
    files_to_remove = [
        get_region_file(),
        get_phones_file(),
        "output/phones.txt"
    ]
    
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"🗑️ Удален файл: {file_path}")
            except Exception as e:
                print(f"❌ Ошибка при удалении файла {file_path}: {e}")

def get_region_name():
    """Получает название региона из базы данных"""
    return get_setting('region', 'Тюмень')  # По умолчанию Тюмень

def get_region_id():
    """Получает ID региона из базы данных"""
    return get_setting('region_id', '4827')  # ID Тюмени по умолчанию

def get_rooms():
    """Получает список выбранных комнат"""
    rooms_str = get_setting('rooms', '1,2,3,4')
    return [int(room) for room in rooms_str.split(',')] if rooms_str else []

def get_min_floor():
    """Получает настройки минимального этажа"""
    value = get_setting('min_floor', '')
    return [int(f) for f in value.split(',')] if value else []

def get_max_floor():
    """Получает настройки максимального этажа"""
    value = get_setting('max_floor', '')
    return [int(f) for f in value.split(',')] if value else []

def get_min_price():
    """Получает минимальную цену"""
    value = get_setting('min_price', '')
    return int(value) if value else None

def get_max_price():
    """Получает максимальную цену"""
    value = get_setting('max_price', '')
    return int(value) if value else None

def set_region(region_name, region_id):
    """Устанавливает регион в настройках"""
    set_setting('region', region_name)
    set_setting('region_id', region_id)
    clear_parsing_data()  # Удаляем старые данные

def set_rooms(rooms):
    """Устанавливает выбранные комнаты"""
    set_setting('rooms', ','.join(map(str, rooms)))
    clear_parsing_data()  # Удаляем старые данные

def set_min_floor(floors):
    """Устанавливает минимальные этажи"""
    value = ','.join(map(str, floors)) if floors else ''
    set_setting('min_floor', value)
    clear_parsing_data()

def set_max_floor(floors):
    """Устанавливает максимальные этажи"""
    value = ','.join(map(str, floors)) if floors else ''
    set_setting('max_floor', value)
    clear_parsing_data()

def set_min_price(price):
    """Устанавливает минимальную цену"""
    set_setting('min_price', str(price) if price is not None else '')
    clear_parsing_data()

def set_max_price(price):
    """Устанавливает максимальную цену"""
    set_setting('max_price', str(price) if price is not None else '')
    clear_parsing_data()

def reset_settings():
    """Сбрасывает все настройки к значениям по умолчанию"""
    # Удаляем все записи из таблицы настроек
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings")
        conn.commit()
    
    # Повторно инициализируем настройки по умолчанию
    init_db()
    clear_parsing_data()
    
    # Восстанавливаем время парсинга из конфига
    set_setting('schedule_time', config.SCHEDULE_TIME)

def get_region_file():
    """Возвращает путь к файлу регионов с ID региона"""
    region_id = get_region_id()
    return f"output/regions_{region_id}.json"

def get_phones_file():
    """Возвращает путь к файлу с номерами"""
    return "output/data.json"

def get_lock_file():
    """Возвращает путь к lock-файлу"""
    return "output/parsing.lock"

def start_parsing():
    """Создает lock-файл для индикации начала парсинга"""
    ensure_output_dir()
    with open(get_lock_file(), 'w') as f:
        f.write("parsing in progress")

def finish_parsing():
    """Удаляет lock-файл после завершения парсинга"""
    lock_file = get_lock_file()
    if os.path.exists(lock_file):
        os.remove(lock_file)

def is_parsing_in_progress():
    """Проверяет, выполняется ли парсинг"""
    return os.path.exists(get_lock_file())

def extract_id_from_url(url):
    """Извлекает ID объявления из URL"""
    match = re.search(r'/(\d+)/?$', url)
    return match.group(1) if match else None

def extract_urls_from_regions(author_type=None):
    """Извлекает URL из файла регионов с фильтрацией по типу автора"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return []
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем новый формат файла
        if "data" in data:
            ads_data = data["data"]
        else:
            # Старый формат для обратной совместимости
            ads_data = data
        
        urls = []
        for item in ads_data:
            # Фильтруем по типу автора, если указан
            if author_type and item.get('author_type') != author_type:
                continue
                
            url = item.get('url')
            if url:
                # Убеждаемся, что URL полный
                if not url.startswith('http'):
                    url = f"https://www.cian.ru{url}"
                urls.append(url)
        
        return urls
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка при чтении файла регионов: {str(e)}")
        return []

def extract_block_id_from_data(announcement_id):
    """Извлекает blockId из данных объявления по ID"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return None
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем новый формат файла
        if "data" in data:
            ads_data = data["data"]
        else:
            # Старый формат для обратной совместимости
            ads_data = data
        
        for item in ads_data:
            url = item.get('url', '')
            if announcement_id in url:
                return item.get('blockId')
        
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка при чтении файла регионов: {str(e)}")
        return None

def extract_direct_phone_from_data(announcement_id):
    """Извлекает прямой телефон из данных объявления по ID"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return None
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем новый формат файла
        if "data" in data:
            ads_data = data["data"]
        else:
            # Старый формат для обратной совместимости
            ads_data = data
        
        for item in ads_data:
            url = item.get('url', '')
            if announcement_id in url:
                return item.get('directPhone')
        
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка при чтении файла регионов: {str(e)}")
        return None

def format_phone(phone):
    """Форматирует телефонный номер в читаемый вид"""
    if not phone:
        return phone
    
    # Удаляем все нецифровые символы кроме +
    clean_phone = re.sub(r'[^\d+]', '', phone)
    
    # Если номер начинается с 8, заменяем на +7
    if clean_phone.startswith('8') and len(clean_phone) == 11:
        clean_phone = '+7' + clean_phone[1:]
    
    # Если номер начинается с 7 и состоит из 11 цифр, добавляем +
    elif clean_phone.startswith('7') and len(clean_phone) == 11:
        clean_phone = '+' + clean_phone
    
    # Форматируем в вид +7 (XXX) XXX-XX-XX
    if clean_phone.startswith('+7') and len(clean_phone) == 12:
        return f"+7 ({clean_phone[2:5]}) {clean_phone[5:8]}-{clean_phone[8:10]}-{clean_phone[10:12]}"
    
    return clean_phone

def sanitize_payload(data):
    """Очищает payload от None значений и преобразует к правильным типам"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if value is not None:
                if isinstance(value, dict):
                    sanitized[key] = sanitize_payload(value)
                elif isinstance(value, list):
                    sanitized[key] = [sanitize_payload(item) for item in value if item is not None]
                else:
                    sanitized[key] = value
        return sanitized
    return data

def get_region_info():
    """Возвращает информацию о регионе из файла"""
    region_file = get_region_file()
    
    if not os.path.exists(region_file):
        return None
    
    try:
        with open(region_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Если файл в новом формате
        if "region" in data and "created_at" in data:
            return {
                "name": data["region"]["name"],
                "id": data["region"]["id"],
                "created_at": data["created_at"]
            }
        # Старый формат - возвращаем базовую информацию
        return {
            "name": get_region_name(),
            "id": get_region_id(),
            "created_at": "unknown"
        }
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка при чтении информации о регионе: {str(e)}")
        return None

def get_setting(key, default=None):
    """Получает значение настройки из базы данных"""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result[0] if result else default

def set_setting(key, value):
    """Устанавливает значение настройки в базе данных"""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()