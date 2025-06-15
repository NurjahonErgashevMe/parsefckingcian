import json
from datetime import datetime
from .config import REGIONS_FILE, CODES_FILE

def extract_urls_to_txt():
    """Извлекает URL из JSON и сохраняет в текстовый файл"""
    print(f"[{datetime.now()}] Извлечение URL из {REGIONS_FILE}...")
    
    try:
        with open(REGIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        urls = [item['url'] for item in data['data']]
        unique_urls = list(set(urls))  # Убираем дубли
        
        with open(CODES_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique_urls))
        
        print(f"[{datetime.now()}] Успешно! Сохранено {len(unique_urls)} URL в {CODES_FILE}")
        return True
    
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка извлечения URL: {str(e)}")
        return False