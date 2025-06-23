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
                # Фильтруем только застройщиков
                developer_data = [item for item in data["data"] if item.get('author_type') == "developer"]
                print(f"Найдено {len(data['data'])} объявлений ({len(developer_data)} от застройщиков) в {region_file}")
                print("="*50)
                print(f"Начинаем парсинг телефонов для застройщиков...")
                print("="*50 + "\n")
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
        success, developer_count = parser_ads.parse_cian_ads(log_callback=print)
        if success:
            print("\n" + "="*50)
            print(f"Данные объявлений сохранены в {region_file}")
            print(f"Найдено {developer_count} объявлений от застройщиков")
            print("Начинаем парсинг телефонов для застройщиков...")
            print("="*50 + "\n")
            parser = phones_parser.CianPhoneParser()
            parser.parse()

if __name__ == "__main__":
    main()