import json
import time
import requests
from requests.exceptions import RequestException

class CianPhoneParser:
    def __init__(self):
        self.api_url = "https://api.cian.ru/newbuilding-dynamic-calltracking/v1/get-dynamic-phone"
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json"
        }
        self.payload_template = {
            "blockId": 13319,
            "platformType": "webDesktop",
            "pageType": "offerCard",
            "placeType": "ContactsAside",
            "refererUrl": "",
            "analyticClientId": "GA1.1.74252020.1749983650",
            "utm": "%7B%22utm_source%22%3A+%22direct%22%2C+%22utm_medium%22%3A+%22None%22%7D"
        }
        self.data_file = "data.json"
        self.codes_file = "codes.txt"
        self.parsed_data = {}
        self.load_existing_data()

    def load_existing_data(self):
        """Загружает ранее спарсенные данные из файла"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.parsed_data = data.get("data", {})
            print(f"Загружено {len(self.parsed_data)} существующих номеров")
        except (FileNotFoundError, json.JSONDecodeError):
            self.parsed_data = {}
            print("Создаем новый файл данных")

    def save_data(self):
        """Сохраняет данные в JSON файл"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump({"data": self.parsed_data}, f, ensure_ascii=False, indent=2)
        print(f"Данные сохранены. Всего номеров: {len(self.parsed_data)}")

    def extract_ids(self):
        """Извлекает ID объявлений из файла с ссылками"""
        ids = []
        try:
            with open(self.codes_file, 'r', encoding='utf-8') as f:
                urls = f.read().splitlines()
            
            for url in urls:
                # Удаляем пробелы и возможные кавычки
                clean_url = url.strip().replace('"', '').replace("'", "")
                
                # Пробуем несколько способов извлечения ID
                if '/flat/' in clean_url:
                    # Способ 1: Разделение URL по частям
                    parts = clean_url.split('/')
                    if 'flat' in parts:
                        idx = parts.index('flat') + 1
                        if idx < len(parts):
                            id_candidate = parts[idx]
                            if id_candidate.isdigit():
                                ids.append(id_candidate)
                                continue
                    
                    # Способ 2: Поиск числовой последовательности в конце URL
                    for part in reversed(parts):
                        if part.isdigit() and len(part) > 5:  # ID обычно длинные
                            ids.append(part)
                            break
                    else:
                        print(f"Не удалось извлечь ID из URL: {clean_url}")
                else:
                    print(f"Неверный формат URL: {clean_url}")
            
            print(f"Найдено {len(ids)} валидных ID")
            return ids
        
        except FileNotFoundError:
            print("Файл codes.txt не найден!")
            return []

    def fetch_phone(self, announcement_id):
        """Получает телефонный номер через API"""
        payload = self.payload_template.copy()
        payload.update({
            "announcementId": announcement_id,
            "locationUrl": f"https://spb.cian.ru/sale/flat/{announcement_id}/"
        })
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        
        except RequestException as e:
            print(f"Ошибка запроса для ID {announcement_id}: {str(e)}")
            return None
        except json.JSONDecodeError:
            print(f"Невалидный JSON для ID {announcement_id}")
            return None

    def parse(self):
        """Основной метод парсинга"""
        announcement_ids = self.extract_ids()
        if not announcement_ids:
            return
        
        request_count = 0
        success_count = 0
        
        for idx, aid in enumerate(announcement_ids, 1):
            # Пропуск уже обработанных ID
            if aid in self.parsed_data:
                print(f"Пропуск существующего ID: {aid}")
                continue
            
            print(f"[{idx}/{len(announcement_ids)}] Запрос для ID: {aid}")
            result = self.fetch_phone(aid)
            request_count += 1
            
            if result and "phone" in result:
                self.parsed_data[aid] = {
                    "phone": result["phone"],
                    "notFormattedPhone": result["notFormattedPhone"]
                }
                success_count += 1
                print(result)
                print(f"Успешно получен номер для {aid}: {result['phone']}")
            else:
                print(f"Не удалось получить номер для {aid}")
            
            # Сохранение каждые 5 успешных запросов
            if success_count % 5 == 0 and success_count > 0:
                self.save_data()
            
            # Пауза после каждых 50 запросов
            if request_count % 50 == 0:
                print(f"Выполнено {request_count} запросов. Ожидание 15 секунд...")
                time.sleep(15)
        
        # Финальное сохранение оставшихся данных
        if success_count > 0:
            self.save_data()
        
        print(f"Парсинг завершен! Успешно обработано: {success_count}/{len(announcement_ids)}")

if __name__ == "__main__":
    parser = CianPhoneParser()
    parser.parse()