import os
import json
import time
from datetime import datetime
import utils  # Используем абсолютный импорт
import parser_ads
import phones_parser

def main():
    """Основная логика приложения"""
    utils.ensure_output_dir()
    region_file = utils.get_region_file()
    
    print("\n" + "="*50)
    print(f"CIAN Parser запущен: {datetime.now()}")
    print("="*50)
    
    # Проверяем наличие файла с данными
    if os.path.exists(region_file):
        try:
            # Проверяем, содержит ли файл данные
            with open(region_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "data" in data and len(data["data"]) > 0:
                print(f"Найдено {len(data['data'])} объявлений. Начинаем парсинг телефонов...")
                parser = phones_parser.CianPhoneParser()
                parser.parse()
                return
                
        except (json.JSONDecodeError, KeyError):
            print("Ошибка чтения файла регионов. Будет выполнен перепарсинг.")
    
    # Если данных нет или файл поврежден
    print("Файл с объявлениями отсутствует или пуст.")
    
    # Проверяем, не запущен ли уже парсинг
    if utils.is_parsing_in_progress():
        print("Парсинг объявлений уже выполняется. Ожидание завершения...")
        
        # Ожидаем завершения парсинга
        while utils.is_parsing_in_progress():
            time.sleep(30)  # Проверяем каждые 30 секунд
            print("Ожидание...")
        
        # После завершения запускаем парсинг телефонов
        print("Парсинг объявлений завершен! Начинаем парсинг телефонов...")
        parser = phones_parser.CianPhoneParser()
        parser.parse()
    else:
        print("Запускаем парсинг объявлений...")
        if parser_ads.parse_cian_ads():
            print("Начинаем парсинг телефонов...")
            # parser = CianPhoneParser(max_phones=0)  # 0 = без ограничений
            parser = phones_parser.CianPhoneParser()
            parser.parse()

if __name__ == "__main__":
    main()