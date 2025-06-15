import cianparser
import json
from datetime import datetime
import utils

def parse_cian_ads(log_callback=None):
    """Парсит объявления с CIAN и сохраняет в regions.json"""
    log_message = f"[{datetime.now()}] Начало парсинга объявлений..."
    _log(log_callback, log_message)
    utils.ensure_output_dir()
    
    try:
        # Создаем lock-файл
        utils.start_parsing()
        
        # Парсим данные
        parser = cianparser.CianParser(location="Тюмень")
        data = parser.get_flats(deal_type="sale", rooms=(1,2,3,4))
        
        # Проверяем и корректируем URL
        for item in data:
            if 'url' in item and not item['url'].startswith('http'):
                item['url'] = f"https://www.cian.ru{item['url']}"
        
        with open(utils.get_region_file(), 'w', encoding='utf-8') as f:
            json.dump({"data": data}, f, ensure_ascii=False, indent=2)
        
        log_message = f"[{datetime.now()}] Успешно! Сохранено {len(data)} объявлений"
        _log(log_callback, log_message)
        return True
    
    except Exception as e:
        log_message = f"[{datetime.now()}] Ошибка парсинга: {str(e)}"
        _log(log_callback, log_message)
        return False
    finally:
        # Всегда удаляем lock-файл
        utils.finish_parsing()

def _log(log_callback, message):
    if log_callback:
        log_callback(message)
    else:
        print(message)