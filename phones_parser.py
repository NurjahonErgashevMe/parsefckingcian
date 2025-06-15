import json
import time
import requests
import re
from datetime import datetime
from requests.exceptions import RequestException
import utils
import config
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class CianPhoneParser:
    def __init__(self, max_phones=50, log_callback=None):
        utils.ensure_output_dir()
        self.parsed_data = {}
        self.max_phones = max_phones
        self.log_callback = log_callback
        self.payload_template = config.PAYLOAD_TEMPLATE.copy()
        self.load_existing_data()
        self.start_time = datetime.now()
        self._log(f"[{self.start_time}] Начало парсинга телефонных номеров")
        self._log(f"ОГРАНИЧЕНИЕ: Будет обработано не более {self.max_phones} номеров")
    
    def _log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def extract_domain(self, url):
        """Извлекает региональный поддомен из URL"""
        match = re.search(r'https?://([a-z]+)\.cian\.ru', url)
        return match.group(1) if match else "www"
    
    def load_existing_data(self):
        phones_file = utils.get_phones_file()
        try:
            with open(phones_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.parsed_data = data.get("data", {})
            self._log(f"Загружено {len(self.parsed_data)} существующих номеров")
        except (FileNotFoundError, json.JSONDecodeError):
            self._log("Файл с номерами не найден, начинаем с чистого листа")
            self.parsed_data = {}
    
    def save_data(self):
        with open(utils.get_phones_file(), 'w', encoding='utf-8') as f:
            json.dump({"data": self.parsed_data}, f, ensure_ascii=False, indent=2)
        self._log(f"[{datetime.now()}] Сохранено {len(self.parsed_data)} номеров")
    
    def activate_with_playwright(self, announcement_id, url):
        """Активирует API через браузер и возвращает новый payload"""
        self._log(f"Активация через браузер для ID: {announcement_id}")
        result = None
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                
                # Переменные для перехвата данных
                intercepted_payload = None
                intercepted_response = None
                
                # Перехватываем запросы к API
                def handle_request(route, request):
                    nonlocal intercepted_payload
                    if request.url == config.API_URL and request.method == "POST":
                        intercepted_payload = request.post_data_json
                    route.continue_()
                
                # Перехватываем ответы API
                def handle_response(response):
                    nonlocal intercepted_response
                    if response.url == config.API_URL and response.request.method == "POST":
                        intercepted_response = response
                
                page.route("**/*", handle_request)
                page.on("response", handle_response)
                
                # Переходим на страницу объявления
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Ожидаем и кликаем кнопку контактов
                try:
                    # Используем правильный селектор data-testid
                    page.wait_for_selector('[data-testid="contacts-button"]', state="visible", timeout=15000)
                    
                    # Дополнительная проверка, что кнопка кликабельна
                    page.evaluate('''() => {
                        const btn = document.querySelector('[data-testid="contacts-button"]');
                        if (btn) {
                            btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                        }
                    }''')
                    
                    # Кликаем с проверкой видимости
                    page.click('[data-testid="contacts-button"]', timeout=5000)
                    self._log("Кнопка контактов нажата")
                except PlaywrightTimeoutError:
                    self._log("Таймаут ожидания кнопки контактов")
                    # Попробуем альтернативный метод клика
                    try:
                        page.evaluate('''() => {
                            const btn = document.querySelector('[data-testid="contacts-button"]');
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }''')
                        self._log("Клик выполнен через evaluate")
                    except:
                        self._log("Не удалось выполнить клик через evaluate")
                
                # Ждем появления номера или API-ответа
                try:
                    # Ожидаем либо появления номера, либо ответа API
                    page.wait_for_selector('.phone-number', state="attached", timeout=10000)
                    self._log("Номер телефона появился на странице")
                except PlaywrightTimeoutError:
                    self._log("Таймаут ожидания номера телефона")
                
                # Дополнительное время для перехвата ответа
                page.wait_for_timeout(5000)
                
                # Получаем результат если перехватили ответ
                if intercepted_response:
                    try:
                        result = intercepted_response.json()
                        self._log(f"Получен ответ API через браузер: {result.get('phone', 'N/A')}")
                    except json.JSONDecodeError:
                        self._log("Ошибка декодирования JSON ответа")
                
                # Если ответ не пришел, пробуем извлечь номер со страницы
                if not result or "phone" not in result:
                    try:
                        phone_element = page.query_selector('.phone-number')
                        if phone_element:
                            phone_text = phone_element.inner_text()
                            self._log(f"Извлечен номер со страницы: {phone_text}")
                            result = {"phone": phone_text, "notFormattedPhone": phone_text}
                    except:
                        self._log("Не удалось извлечь номер со страницы")
                
                # Закрываем браузер
                browser.close()
                
                # Возвращаем результат и payload
                if intercepted_payload:
                    # Удаляем уникальные поля из payload
                    clean_payload = {k: v for k, v in intercepted_payload.items() 
                                    if k not in ["announcementId", "locationUrl", "refererUrl"]}
                    return result, clean_payload
        
        except Exception as e:
            self._log(f"Ошибка при работе с браузером: {str(e)}")
        
        return None, None

    def fetch_phone_with_retry(self, announcement_id, url):
        """Получает телефонный номер через API с повторными попытками и активацией через браузер"""
        domain = self.extract_domain(url)
        location_url = f"https://{domain}.cian.ru/sale/flat/{announcement_id}/"
        
        payload = self.payload_template.copy()
        payload.update({
            "announcementId": announcement_id,
            "locationUrl": location_url,
            "refererUrl": location_url
        })
        
        attempts = 0
        max_attempts = 3
        
        while attempts < max_attempts:
            try:
                response = requests.post(
                    config.API_URL,
                    headers=config.HEADERS,
                    json=payload,
                    timeout=15
                )
                response.raise_for_status()
                data = response.json()
                
                if "phone" in data and data["phone"]:
                    return data
                else:
                    self._log(f"Попытка {attempts+1}: Пустой ответ для ID {announcement_id}")
            
            except RequestException as e:
                self._log(f"Попытка {attempts+1}: Ошибка запроса для ID {announcement_id}: {str(e)}")
            except json.JSONDecodeError:
                self._log(f"Попытка {attempts+1}: Невалидный JSON для ID {announcement_id}")
            
            attempts += 1
            if attempts < max_attempts:
                time.sleep(2)
        
        # Если обычные попытки не удались, пробуем активацию через браузер
        self._log(f"Активация через браузер для ID {announcement_id}")
        result, new_payload = self.activate_with_playwright(announcement_id, url)
        
        # Обновляем payload если получили новый
        if new_payload:
            self.payload_template.update(new_payload)
            self._log(f"Обновлен payload_template: {json.dumps(self.payload_template, indent=2)}")
        
        # Если получили результат через браузер
        if result and "phone" in result and result["phone"]:
            return result
        
        # Делаем финальный запрос после активации
        try:
            response = requests.post(
                config.API_URL,
                headers=config.HEADERS,
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            self._log(f"Финальный запрос после активации не удался: {str(e)}")
        
        return None
    
    def export_phones_to_txt(self):
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
        
        self._log(f"Номера экспортированы в {txt_file}")
        self._log(f"Успешных номеров: {success_count}/{len(self.parsed_data)}")
    
    def parse(self):
        urls = utils.extract_urls_from_regions()
        if not urls:
            self._log("Нет URL для обработки!")
            return
        
        total_urls = len(urls)
        request_count = 0
        success_count = 0
        processed_count = 0
        
        self._log(f"Всего URL для обработки: {total_urls}")
        self._log(f"Ограничение на количество номеров: {self.max_phones}")
        
        for idx, url in enumerate(urls, 1):
            if processed_count >= self.max_phones:
                self._log(f"\nДостигнуто ограничение в {self.max_phones} номеров. Парсинг остановлен.")
                break
            
            aid = utils.extract_id_from_url(url)
            if not aid:
                self._log(f"Не удалось извлечь ID из URL: {url}")
                continue
            
            if aid in self.parsed_data:
                self._log(f"[{idx}/{total_urls}] Пропуск существующего ID: {aid}")
                continue
            
            self._log(f"[{idx}/{total_urls}] Запрос для ID: {aid}")
            result = self.fetch_phone_with_retry(aid, url)
            request_count += 1
            processed_count += 1
            
            if result and "phone" in result:
                self.parsed_data[aid] = {
                    "phone": result["phone"],
                    "notFormattedPhone": result.get("notFormattedPhone", "")
                }
                success_count += 1
                self._log(f"Успешно: {aid} => {result['phone']}")
            else:
                self.parsed_data[aid] = {"phone": "не удалось получить"}
                self._log(f"Не удалось получить номер для {aid}")
            
            if idx % 5 == 0:
                self.save_data()
            
            if request_count % 50 == 0:
                self._log(f"Выполнено {request_count} запросов. Ожидание 15 секунд...")
                time.sleep(15)
        
        self.save_data()
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        self._log("\n" + "="*50)
        self._log(f"Парсинг завершен: {end_time}")
        self._log(f"Общее время выполнения: {duration}")
        self._log(f"Обработано номеров: {processed_count}/{self.max_phones}")
        self._log(f"Успешных номеров: {success_count}/{processed_count}")
        self._log("="*50 + "\n")
        
        self.export_phones_to_txt()