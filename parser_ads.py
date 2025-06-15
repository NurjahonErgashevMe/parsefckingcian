import cianparser
import json
from datetime import datetime
import utils  # Используем абсолютный импорт

def parse_cian_ads():
    """Парсит объявления с CIAN и сохраняет в regions.json"""
    print(f"[{datetime.now()}] Начало парсинга объявлений...")
    utils.ensure_output_dir()
    
    try:
        # Создаем lock-файл
        utils.start_parsing()
        
        # Парсим данные
        parser = cianparser.CianParser(location="Тюмень")
        data = parser.get_flats(deal_type="sale", rooms=(1,2,3,4))
        
        # Сохраняем результат
        with open(utils.get_region_file(), 'w', encoding='utf-8') as f:
            json.dump({"data": data}, f, ensure_ascii=False, indent=2)
        
        print(f"[{datetime.now()}] Успешно! Сохранено {len(data)} объявлений")
        return True
    
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка парсинга: {str(e)}")
        return False
    finally:
        # Всегда удаляем lock-файл
        utils.finish_parsing()