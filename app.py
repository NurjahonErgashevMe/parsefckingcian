import os
import json
import time
from datetime import datetime
import utils
import parser_ads
import phones_parser

def main():
    utils.ensure_output_dir()
    region_file = utils.get_region_file()
    
    print("\n" + "="*50)
    print(f"CIAN Parser запущен: {datetime.now()}")
    print("="*50)
    
    # Проверяем наличие файла с данными
    if os.path.exists(region_file):
        try:
            with open(region_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "data" in data and len(data["data"]) > 0:
                print(f"Найдено {len(data['data'])} объявлений. Начинаем парсинг телефонов...")
                parser = phones_parser.CianPhoneParser()
                parser.parse()
                return
        
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Ошибка чтения файла регионов: {str(e)}. Будет выполнен перепарсинг.")
    
    print("Файл с объявлениями отсутствует или пуст.")
    
    if utils.is_parsing_in_progress():
        print("Парсинг объявлений уже выполняется. Ожидание завершения...")
        
        while utils.is_parsing_in_progress():
            time.sleep(30)
            print("Ожидание...")
        
        print("Парсинг объявлений завершен! Начинаем парсинг телефонов...")
        parser = phones_parser.CianPhoneParser()
        parser.parse()
    else:
        print("Запускаем парсинг объявлений...")
        if parser_ads.parse_cian_ads():
            print("Начинаем парсинг телефонов...")
            parser = phones_parser.CianPhoneParser()
            parser.parse()

if __name__ == "__main__":
    main()