import json
import time
import requests
from datetime import datetime
from requests.exceptions import RequestException
import utils

API_URL = "https://api.cian.ru/newbuilding-dynamic-calltracking/v1/get-dynamic-phone"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}
PAYLOAD_TEMPLATE = {
    "blockId": 13319,
    "platformType": "webDesktop",
    "pageType": "offerCard",
    "placeType": "ContactsAside",
    "refererUrl": "",
    "analyticClientId": "GA1.1.74252020.1749983650",
    "utm": "%7B%22utm_source%22%3A+%22direct%22%2C+%22utm_medium%22%3A+%22None%22%7D"
}

class CianPhoneParser:
    def __init__(self, max_phones=200):
        utils.ensure_output_dir()
        self.parsed_data = {}
        self.max_phones = max_phones  # Ограничение количества номеров
        self.load_existing_data()
        self.start_time = datetime.now()
        print(f"[{self.start_time}] Начало парсинга телефонных номеров")
        print(f"ОГРАНИЧЕНИЕ: Будет обработано не более {self.max_phones} номеров")
    
    def load_existing_data(self):
        """Загружает ранее спарсенные данные"""
        phones_file = utils.get_phones_file()
        try:
            with open(phones_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.parsed_data = data.get("data", {})
            print(f"Загружено {len(self.parsed_data)} существующих номеров")
        except (FileNotFoundError, json.JSONDecodeError):
            self.parsed_data = {}
    
    def save_data(self):
        """Сохраняет данные в JSON файл"""
        with open(utils.get_phones_file(), 'w', encoding='utf-8') as f:
            json.dump({"data": self.parsed_data}, f, ensure_ascii=False, indent=2)
        print(f"[{datetime.now()}] Сохранено {len(self.parsed_data)} номеров")
    
    def fetch_phone_with_retry(self, announcement_id):
        """Получает телефонный номер через API с повторными попытками"""
        payload = PAYLOAD_TEMPLATE.copy()
        payload.update({
            "announcementId": announcement_id,
            "locationUrl": f"https://spb.cian.ru/sale/flat/{announcement_id}/"
        })
        
        attempts = 0
        max_attempts = 5
        
        while attempts < max_attempts:
            try:
                response = requests.post(
                    API_URL,
                    headers=HEADERS,
                    json=payload,
                    timeout=15
                )
                response.raise_for_status()
                data = response.json()
                
                if "phone" in data and data["phone"]:
                    return data
                else:
                    print(f"Попытка {attempts+1}: Пустой ответ для ID {announcement_id}")
            
            except RequestException as e:
                print(f"Попытка {attempts+1}: Ошибка запроса для ID {announcement_id}: {str(e)}")
            except json.JSONDecodeError:
                print(f"Попытка {attempts+1}: Невалидный JSON для ID {announcement_id}")
            
            attempts += 1
            if attempts < max_attempts:
                time.sleep(5)  # Пауза перед следующей попыткой
        
        return None
    
    def export_phones_to_txt(self):
        """Экспортирует номера в текстовый файл"""
        txt_file = "output/phones.txt"
        success_count = sum(1 for v in self.parsed_data.values() if v.get("phone") and v["phone"] != "не удалось получить")
        
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"Дата парсинга: {self.start_time}\n")
            f.write(f"Обработано объявлений: {len(self.parsed_data)}\n")
            f.write(f"Успешно полученных номеров: {success_count}\n")
            f.write(f"Время выполнения: {datetime.now() - self.start_time}\n")
            f.write(f"Ограничение на количество: {self.max_phones}\n\n")
            
            f.write("Спарсенные номера:\n")
            f.write("="*50 + "\n")
            
            for aid, data in self.parsed_data.items():
                phone = data.get("phone", "не удалось получить")
                f.write(f"ID: {aid}\nТелефон: {phone}\n")
                f.write("-"*50 + "\n")
        
        print(f"Номера экспортированы в {txt_file}")
        print(f"Успешных номеров: {success_count}/{len(self.parsed_data)}")
    
    def parse(self):
        """Основной метод парсинга телефонных номеров"""
        # Извлекаем URL из регионов
        urls = utils.extract_urls_from_regions()
        if not urls:
            print("Нет URL для обработки!")
            return
        
        total_urls = len(urls)
        request_count = 0
        success_count = 0
        processed_count = 0  # Счетчик обработанных номеров
        
        print(f"Всего URL для обработки: {total_urls}")
        print(f"Ограничение на количество номеров: {self.max_phones}")
        
        for idx, url in enumerate(urls, 1):
            # Проверяем достижение лимита
            if processed_count >= self.max_phones:
                print(f"\nДостигнуто ограничение в {self.max_phones} номеров. Парсинг остановлен.")
                break
            
            aid = utils.extract_id_from_url(url)
            if not aid:
                continue
            
            # Пропускаем уже обработанные
            if aid in self.parsed_data:
                print(f"[{idx}/{total_urls}] Пропуск существующего ID: {aid}")
                continue
            
            print(f"[{idx}/{total_urls}] Запрос для ID: {aid}")
            result = self.fetch_phone_with_retry(aid)
            request_count += 1
            processed_count += 1  # Увеличиваем счетчик обработанных
            
            if result and "phone" in result:
                self.parsed_data[aid] = {
                    "phone": result["phone"],
                    "notFormattedPhone": result["notFormattedPhone"]
                }
                success_count += 1
                print(f"Успешно: {aid} => {result['phone']}")
            else:
                # Сохраняем факт неудачи
                self.parsed_data[aid] = {"phone": "не удалось получить"}
                print(f"Не удалось получить номер для {aid} после 5 попыток")
            
            # Сохранение каждые 5 запросов
            if idx % 5 == 0:
                self.save_data()
            
            # Пауза после каждых 50 запросов
            if request_count % 50 == 0:
                print(f"Выполнено {request_count} запросов. Ожидание 15 секунд...")
                time.sleep(15)
        
        # Финальное сохранение
        self.save_data()
        
        # Расчет времени выполнения
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        print("\n" + "="*50)
        print(f"Парсинг завершен: {end_time}")
        print(f"Общее время выполнения: {duration}")
        print(f"Обработано номеров: {processed_count}/{self.max_phones}")
        print(f"Успешных номеров: {success_count}/{processed_count}")
        print("="*50 + "\n")
        
        # Экспорт в текстовый файл
        self.export_phones_to_txt()