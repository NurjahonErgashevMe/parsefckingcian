import json
import time
import os
import requests
import re
from datetime import datetime
from requests.exceptions import RequestException
import utils
import config
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class CianPhoneParser:
    def __init__(self, max_phones=50, log_callback=None, clear_existing=False):
        utils.ensure_output_dir()
        self.parsed_data = {}
        self.max_phones = max_phones
        self.log_callback = log_callback
        self.current_headers = config.HEADERS.copy()
        self.current_payload_template = config.PAYLOAD_TEMPLATE.copy()
        
        # Очистка старых файлов при необходимости
        if clear_existing:
            self._clear_existing_files()
            
        self.load_existing_data()
        self.start_time = datetime.now()
        self._log(f"[{self.start_time}] Начало парсинга телефонных номеров")
        self._log(f"ОГРАНИЧЕНИЕ: Будет обработано не более {self.max_phones} номеров")
        if clear_existing:
            self._log("Старые файлы данных были удалены")
        
        # Выполняем активацию через браузер при инициализации
        self._activate_browser()

    def _activate_browser(self):
        """Активирует парсер через браузер: перехватывает запрос к API, чтобы получить актуальные данные"""
        self._log("Запуск браузера для активации парсера...")
        
        # Получаем список URL, берем первый для активации
        urls = utils.extract_urls_from_regions()
        if not urls:
            url = "https://tyumen.cian.ru/sale/flat/307997699/"  # дефолтный URL
            self._log(f"Нет URL в регионах, используем дефолтный URL: {url}")
        else:
            url = urls[0]
            self._log(f"Используем первый URL из списка для активации: {url}")
        
        intercepted_headers = None
        intercepted_payload = None
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                
                # Перехватываем запросы к API
                def handle_request(route, request):
                    nonlocal intercepted_headers, intercepted_payload
                    if request.url == config.API_URL and request.method == "POST":
                        intercepted_headers = dict(request.headers)
                        intercepted_payload = request.post_data_json
                        self._log(f"Перехвачен запрос на API: {request.url}")
                    route.continue_()
                
                page.route("**/*", handle_request)
                
                # Переходим на страницу объявления
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Кликаем кнопку контактов
                try:
                    page.wait_for_selector('[data-testid="contacts-button"]', state="visible", timeout=15000)
                    page.click('[data-testid="contacts-button"]')
                    self._log("Кнопка контактов нажата")
                except Exception as e:
                    self._log(f"Ошибка при клике на кнопку: {str(e)}")
                
                # Ждем появления номера
                try:
                    page.wait_for_selector('[data-testid="PhoneLink"], .phone-number', state="attached", timeout=10000)
                    self._log("Номер телефона появился на странице")
                except:
                    self._log("Таймаут ожидания номера телефона")
                
                # Дополнительное время для перехвата
                page.wait_for_timeout(5000)
                browser.close()
        
        except Exception as e:
            self._log(f"Ошибка при активации через браузер: {str(e)}")
        
        # Обновляем данные на основе перехваченных значений
        if intercepted_headers and intercepted_payload:
            self._log("Обновляем заголовки и payload на основе перехваченных данных")
            
            # Обновляем заголовки
            self.current_headers.update({
                "Cookie": intercepted_headers.get("cookie", self.current_headers.get("Cookie", "")),
                "Referer": intercepted_headers.get("referer", self.current_headers.get("Referer", "")),
                "Origin": intercepted_headers.get("origin", self.current_headers.get("Origin", ""))
            })
            
            # Обновляем payload
            self.current_payload_template.update({
                "blockId": intercepted_payload.get("blockId", self.current_payload_template.get("blockId", 0)),
                "platformType": intercepted_payload.get("platformType", self.current_payload_template.get("platformType", "")),
                "pageType": intercepted_payload.get("pageType", self.current_payload_template.get("pageType", "")),
                "placeType": intercepted_payload.get("placeType", self.current_payload_template.get("placeType", "")),
                "refererUrl": intercepted_payload.get("refererUrl", self.current_payload_template.get("refererUrl", "")),
                # "analyticClientId": intercepted_payload.get("analyticClientId", self.current_payload_template.get("analyticClientId", "G12.12321.123121D")),
                "utm": intercepted_payload.get("utm", self.current_payload_template.get("utm", ""))
            })
            
            # Логируем обновленные данные
            self._log(f"Обновленные заголовки: {json.dumps(self.current_headers, indent=2)}")
            self._log(f"Обновленный payload: {json.dumps(self.current_payload_template, indent=2)}")
        else:
            self._log("Не удалось перехватить данные, используем значения по умолчанию")

    def _clear_existing_files(self):
        """Удаляет существующие файлы данных, чтобы начать парсинг заново"""
        files_to_remove = [
            utils.get_phones_file(),  # data.json
            "output/phones.txt"       # файл экспорта
        ]
        
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self._log(f"Удален файл: {file_path}")
                except Exception as e:
                    self._log(f"Ошибка при удалении файла {file_path}: {str(e)}")
    
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
            if os.path.exists(phones_file):
                with open(phones_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.parsed_data = data.get("data", {})
                self._log(f"Загружено {len(self.parsed_data)} существующих номеров")
            else:
                self._log("Файл с номерами не найден, начинаем с чистого листа")
        except (FileNotFoundError, json.JSONDecodeError):
            self._log("Файл с номерами не найден или поврежден, начинаем с чистого листа")
            self.parsed_data = {}
    
    def save_data(self):
        with open(utils.get_phones_file(), 'w', encoding='utf-8') as f:
            json.dump({"data": self.parsed_data}, f, ensure_ascii=False, indent=2)
        self._log(f"[{datetime.now()}] Сохранено {len(self.parsed_data)} номеров")
    
    def fetch_phone_with_retry(self, announcement_id, url, block_id=None, direct_phone=None):
        """Получает телефонный номер через API с повторными попытками"""
        # Если есть прямой телефон, используем его
        if direct_phone:
            formatted_phone = utils.format_phone(direct_phone)
            not_formatted_phone = re.sub(r'\D', '', direct_phone)
            self._log(f"Используем прямой телефон для ID {announcement_id}: {formatted_phone}")
            return {
                "phone": formatted_phone,
                "notFormattedPhone": not_formatted_phone
            }
        
        domain = self.extract_domain(url)
        location_url = f"https://tyumen.cian.ru/sale/flat/{announcement_id}/"
        
        headers = utils.sanitize_payload(self.current_headers)
        payload = self.current_payload_template.copy()
        payload = utils.sanitize_payload(payload)
        
        # Если передан block_id (из данных объявления), используем его
        if block_id is not None:
            payload["blockId"] = int(block_id)
        
        payload.update({
            "announcementId": int(announcement_id),
            "locationUrl": location_url,
        })
        
        attempts = 0
        max_attempts = 6  # Увеличили количество попыток до 6
        
        self._log(f"URL запроса: {location_url}")
        self._log(f"Payload: {json.dumps(payload, indent=2)}")
        
        while attempts < max_attempts:
            try:
                response = requests.post(
                    config.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=15
                )
                response.raise_for_status()
                data = response.json()
                
                if "phone" in data and data["phone"]:
                    # Форматируем телефон перед возвратом
                    data["phone"] = utils.format_phone(data["phone"])
                    return data
                else:
                    self._log(f"Попытка {attempts+1}/{max_attempts}: Пустой ответ для ID {announcement_id}")
            
            except RequestException as e:
                self._log(f"Попытка {attempts+1}/{max_attempts}: Ошибка запроса для ID {announcement_id}: {str(e)}")
            except json.JSONDecodeError:
                self._log(f"Попытка {attempts+1}/{max_attempts}: Невалидный JSON для ID {announcement_id}")
            
            attempts += 1
            if attempts < max_attempts:
                time.sleep(2)
        
        # Если все 6 попыток не удались, пробуем получить номер через браузер
        self._log(f"Все {max_attempts} попыток API не удались. Пробуем Playwright для ID {announcement_id}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                
                # Переходим на страницу объявления
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Кликаем кнопку контактов
                try:
                    page.wait_for_selector('[data-testid="contacts-button"]', state="visible", timeout=10000)
                    page.click('[data-testid="contacts-button"]')
                except:
                    try:
                        page.evaluate('''() => {
                            const btn = document.querySelector('[data-testid="contacts-button"]');
                            if (btn) btn.click();
                        }''')
                    except:
                        pass
                
                # Ждем появления номера
                try:
                    page.wait_for_selector('[data-testid="PhoneLink"], .phone-number', state="attached", timeout=10000)
                except:
                    pass
                
                # Извлекаем номер
                phone_element = page.query_selector('[data-testid="PhoneLink"], .phone-number')
                if phone_element:
                    phone_text = phone_element.inner_text()
                    # Очищаем номер от лишних символов
                    phone_text = re.sub(r'[^\d+]', '', phone_text)
                    self._log(f"Извлечен номер со страницы: {phone_text}")
                    
                    # Форматируем телефон
                    formatted_phone = utils.format_phone(phone_text)
                    return {
                        "phone": formatted_phone,
                        "notFormattedPhone": phone_text
                    }
                
                browser.close()
        except Exception as e:
            self._log(f"Ошибка при получении номера через браузер: {str(e)}")
        
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
            
            # Извлекаем данные для этого объявления
            block_id = utils.extract_block_id_from_data(aid)
            direct_phone = utils.extract_direct_phone_from_data(aid)
            
            self._log(f"[{idx}/{total_urls}] Запрос для ID: {aid}")
            self._log(f"BlockId: {block_id}, Прямой телефон: {direct_phone}")
            
            # Если есть прямой телефон, используем его
            if direct_phone:
                formatted_phone = utils.format_phone(direct_phone)
                not_formatted_phone = re.sub(r'\D', '', direct_phone)
                
                self.parsed_data[aid] = {
                    "phone": formatted_phone,
                    "notFormattedPhone": not_formatted_phone,
                    "source": "direct"
                }
                success_count += 1
                processed_count += 1
                self._log(f"Использован прямой телефон: {formatted_phone}")
                # Сохраняем прогресс
                if idx % 5 == 0:
                    self.save_data()
                continue
            
            result = self.fetch_phone_with_retry(aid, url, block_id, direct_phone)
            request_count += 1
            processed_count += 1
            
            if result and "phone" in result and result["phone"]:
                self.parsed_data[aid] = {
                    "phone": result["phone"],
                    "notFormattedPhone": result.get("notFormattedPhone", re.sub(r'\D', '', result["phone"])),
                    "source": "api"
                }
                success_count += 1
                self._log(f"Успешно: {aid} => {result['phone']}")
            else:
                self.parsed_data[aid] = {
                    "phone": "не удалось получить",
                    "notFormattedPhone": "",
                    "source": "failed"
                }
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