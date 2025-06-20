import json
import time
import os
import re
from datetime import datetime
import utils
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class CianPhoneParser:
    def __init__(self, max_phones=50, log_callback=None, clear_existing=False):
        utils.ensure_output_dir()
        self.parsed_data = {}
        self.max_phones = max_phones
        self.log_callback = log_callback
        
        # Очистка старых файлов при необходимости
        if clear_existing:
            self._clear_existing_files()
            
        self.load_existing_data()
        self.start_time = datetime.now()
        self._log(f"[{self.start_time}] Начало парсинга телефонных номеров")
        self._log(f"ОГРАНИЧЕНИЕ: Будет обработано не более {self.max_phones} номеров")
        self._log("Режим парсинга: ТОЛЬКО через браузер (Playwright)")
        if clear_existing:
            self._log("Старые файлы данных были удалены")

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

    def fetch_phone_via_browser(self, announcement_id, url):
        """Получает телефонный номер ТОЛЬКО через браузер"""
        self._log(f"Получение номера через браузер для ID {announcement_id}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                    locale='ru-RU'
                )
                
                page = context.new_page()
                
                # Переходим на страницу объявления
                self._log(f"Загружаем страницу: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Ждем загрузки страницы
                page.wait_for_timeout(3000)
                
                # Проверяем, что страница загрузилась корректно
                page_title = page.title()
                if "Cian" not in page_title and "объявление" not in page_title.lower():
                    self._log(f"Предупреждение: подозрительный заголовок страницы: {page_title}")
                
                # Кликаем кнопку контактов - пробуем несколько селекторов
                contact_selectors = [
                    '[data-testid="contacts-button"]',
                    '[data-name="OfferCardCallButton"]',
                    '.offer-card-call-button',
                    'button[class*="contact"]',
                    'button:has-text("Показать телефон")',
                    'button:has-text("Контакты")',
                    'a:has-text("Показать телефон")'
                ]
                
                contact_clicked = False
                for selector in contact_selectors:
                    try:
                        if page.query_selector(selector):
                            self._log(f"Найдена кнопка контактов по селектору: {selector}")
                            page.wait_for_selector(selector, state="visible", timeout=5000)
                            page.click(selector, timeout=5000)
                            self._log("Кнопка контактов нажата")
                            contact_clicked = True
                            break
                    except Exception as e:
                        self._log(f"Селектор {selector} не сработал: {str(e)}")
                        continue
                
                # Если обычный клик не сработал, пробуем JavaScript
                if not contact_clicked:
                    self._log("Пробуем кликнуть через JavaScript")
                    try:
                        result = page.evaluate('''() => {
                            const selectors = [
                                '[data-testid="contacts-button"]',
                                '[data-name="OfferCardCallButton"]',
                                '.offer-card-call-button',
                                'button[class*="contact"]'
                            ];
                            
                            for (let selector of selectors) {
                                const btn = document.querySelector(selector);
                                if (btn) {
                                    btn.click();
                                    return selector;
                                }
                            }
                            
                            // Ищем по тексту
                            const buttons = Array.from(document.querySelectorAll('button, a'));
                            for (let btn of buttons) {
                                if (btn.textContent.includes('телефон') || 
                                    btn.textContent.includes('Контакт') ||
                                    btn.textContent.includes('Показать')) {
                                    btn.click();
                                    return 'text-based';
                                }
                            }
                            return null;
                        }''')
                        
                        if result:
                            self._log(f"Кнопка нажата через JavaScript: {result}")
                            contact_clicked = True
                        else:
                            self._log("Кнопка контактов не найдена")
                    except Exception as e:
                        self._log(f"Ошибка при клике через JavaScript: {str(e)}")
                
                # Ждем появления номера телефона
                if contact_clicked:
                    self._log("Ожидаем появления номера телефона...")
                    try:
                        phone_selectors = [
                            '[data-testid="PhoneLink"]',
                            '.phone-number',
                            '[href^="tel:"]',
                            'a[class*="phone"]',
                            'span[class*="phone"]',
                            'div[class*="phone"]'
                        ]
                        
                        # Ждем любой из селекторов телефона
                        selector_found = None
                        for selector in phone_selectors:
                            try:
                                page.wait_for_selector(selector, state="attached", timeout=3000)
                                selector_found = selector
                                self._log(f"Номер найден по селектору: {selector}")
                                break
                            except:
                                continue
                        
                        if not selector_found:
                            self._log("Номер телефона не появился по стандартным селекторам")
                    except:
                        self._log("Таймаут ожидания номера телефона")
                
                # Дополнительное время для полной загрузки
                page.wait_for_timeout(5000)
                
                # Пытаемся извлечь номер разными способами
                phone_text = None
                found_method = None
                
                # Способ 1: Стандартные селекторы
                phone_selectors = [
                    ('[data-testid="PhoneLink"]', 'PhoneLink'),
                    ('.phone-number', 'phone-number class'),
                    ('[href^="tel:"]', 'tel: link'),
                    ('a[class*="phone"]', 'phone link'),
                    ('span[class*="phone"]', 'phone span'),
                    ('div[class*="phone"]', 'phone div')
                ]
                
                for selector, method in phone_selectors:
                    try:
                        elements = page.query_selector_all(selector)
                        for element in elements:
                            if selector == '[href^="tel:"]':
                                phone_text = element.get_attribute('href').replace('tel:', '').strip()
                            else:
                                phone_text = element.inner_text().strip()
                            
                            if phone_text and len(re.sub(r'\D', '', phone_text)) >= 10:
                                found_method = method
                                self._log(f"Номер найден через {method}: {phone_text}")
                                break
                        if phone_text:
                            break
                    except Exception as e:
                        continue
                
                # Способ 2: Поиск по регулярным выражениям на всей странице
                if not phone_text:
                    self._log("Ищем номер через регулярные выражения на всей странице")
                    try:
                        all_text = page.inner_text('body')
                        
                        # Российские номера телефонов - различные форматы
                        phone_patterns = [
                            r'\+7[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',
                            r'8[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',
                            r'\+7\d{10}',
                            r'8\d{10}',
                            r'\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}'
                        ]
                        
                        for pattern in phone_patterns:
                            matches = re.findall(pattern, all_text)
                            # Фильтруем совпадения - исключаем очевидно неправильные номера
                            for match in matches:
                                clean_match = re.sub(r'\D', '', match)
                                if len(clean_match) == 11 and (clean_match.startswith('8') or clean_match.startswith('7')):
                                    phone_text = match
                                    found_method = f'regex pattern: {pattern}'
                                    self._log(f"Номер найден через регулярное выражение: {phone_text}")
                                    break
                                elif len(clean_match) == 10 and not clean_match.startswith('0'):
                                    phone_text = match
                                    found_method = f'regex pattern: {pattern}'
                                    self._log(f"Номер найден через регулярное выражение: {phone_text}")
                                    break
                            if phone_text:
                                break
                    except Exception as e:
                        self._log(f"Ошибка при поиске через регулярные выражения: {str(e)}")
                
                # Способ 3: Поиск в HTML коде страницы
                if not phone_text:
                    self._log("Ищем номер в HTML коде страницы")
                    try:
                        html_content = page.content()
                        
                        # Ищем в атрибутах href="tel:"
                        tel_pattern = r'href="tel:([^"]+)"'
                        tel_matches = re.findall(tel_pattern, html_content)
                        for match in tel_matches:
                            clean_match = re.sub(r'\D', '', match)
                            if len(clean_match) >= 10:
                                phone_text = match
                                found_method = 'HTML tel: attribute'
                                self._log(f"Номер найден в HTML tel: атрибуте: {phone_text}")
                                break
                        
                        # Ищем в data-атрибутах
                        if not phone_text:
                            data_patterns = [
                                r'data-phone="([^"]+)"',
                                r'data-number="([^"]+)"',
                                r'data-contact="([^"]+)"'
                            ]
                            
                            for pattern in data_patterns:
                                matches = re.findall(pattern, html_content)
                                for match in matches:
                                    clean_match = re.sub(r'\D', '', match)
                                    if len(clean_match) >= 10:
                                        phone_text = match
                                        found_method = f'HTML data attribute: {pattern}'
                                        self._log(f"Номер найден в data-атрибуте: {phone_text}")
                                        break
                                if phone_text:
                                    break
                    except Exception as e:
                        self._log(f"Ошибка при поиске в HTML: {str(e)}")
                
                browser.close()
                
                if phone_text:
                    # Очищаем номер от лишних символов и форматируем
                    clean_phone = re.sub(r'[^\d+]', '', phone_text)
                    
                    # Проверяем, что это похоже на российский номер
                    if len(clean_phone) >= 10:
                        formatted_phone = utils.format_phone(clean_phone)
                        
                        self._log(f"✓ Успешно извлечен номер: {formatted_phone} (метод: {found_method})")
                        return {
                            "phone": formatted_phone,
                            "notFormattedPhone": clean_phone,
                            "source": "browser",
                            "method": found_method
                        }
                    else:
                        self._log(f"Найденный текст не похож на номер телефона: {phone_text}")
                        return None
                else:
                    self._log("✗ Номер телефона не найден на странице")
                    return None
                    
        except Exception as e:
            self._log(f"✗ Ошибка при получении номера через браузер: {str(e)}")
            return None
    
    def fetch_phone(self, announcement_id, url, direct_phone=None):
        """Получает телефонный номер - ТОЛЬКО через браузер или прямой номер"""
        
        # Если есть прямой телефон, используем его
        if direct_phone:
            formatted_phone = utils.format_phone(direct_phone)
            not_formatted_phone = re.sub(r'\D', '', direct_phone)
            self._log(f"Используем прямой телефон для ID {announcement_id}: {formatted_phone}")
            return {
                "phone": formatted_phone,
                "notFormattedPhone": not_formatted_phone,
                "source": "direct",
                "method": "direct_from_data"
            }
        
        # Получаем номер через браузер
        return self.fetch_phone_via_browser(announcement_id, url)

    def export_phones_to_txt(self):
        txt_file = "output/phones.txt"
        success_count = sum(1 for v in self.parsed_data.values() if v.get("phone") and v["phone"] != "не удалось получить")
        
        # Группируем по источникам и методам
        sources = {}
        methods = {}
        for data in self.parsed_data.values():
            if data.get("phone") and data["phone"] != "не удалось получить":
                source = data.get("source", "unknown")
                method = data.get("method", "unknown")
                
                if source not in sources:
                    sources[source] = 0
                sources[source] += 1
                
                if method not in methods:
                    methods[method] = 0
                methods[method] += 1
        
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"Дата парсинга: {self.start_time}\n")
            f.write(f"Режим парсинга: ТОЛЬКО браузер (Playwright)\n")
            f.write(f"Обработано объявлений: {len(self.parsed_data)}\n")
            f.write(f"Успешно полученных номеров: {success_count}\n")
            f.write(f"Время выполнения: {datetime.now() - self.start_time}\n")
            f.write(f"Ограничение на количество: {self.max_phones}\n")
            
            f.write(f"\nСтатистика по источникам:\n")
            for source, count in sources.items():
                f.write(f"  {source}: {count} номеров\n")
            
            f.write(f"\nСтатистика по методам извлечения:\n")
            for method, count in methods.items():
                f.write(f"  {method}: {count} номеров\n")
            f.write("\n")
            
            f.write("Спарсенные номера:\n")
            f.write("="*50 + "\n")
            
            for aid, data in self.parsed_data.items():
                phone = data.get("phone", "не удалось получить")
                source = data.get("source", "unknown")
                method = data.get("method", "unknown")
                f.write(f"ID: {aid}\nТелефон: {phone}\nИсточник: {source}\nМетод: {method}\n")
                f.write("-"*50 + "\n")
        
        self._log(f"Номера экспортированы в {txt_file}")
        self._log(f"Успешных номеров: {success_count}/{len(self.parsed_data)}")
        self._log(f"Статистика по источникам: {sources}")
        self._log(f"Статистика по методам: {methods}")
    
    def parse(self):
        urls = utils.extract_urls_from_regions()
        if not urls:
            self._log("Нет URL для обработки!")
            return
        
        total_urls = len(urls)
        success_count = 0
        processed_count = 0
        
        self._log(f"Всего URL для обработки: {total_urls}")
        self._log(f"Ограничение на количество номеров: {self.max_phones}")
        self._log("Парсинг ТОЛЬКО через браузер - API полностью отключен!")
        
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
            
            # Извлекаем прямой телефон из данных (если есть)
            direct_phone = utils.extract_direct_phone_from_data(aid)
            
            self._log(f"\n[{idx}/{total_urls}] ===== Обработка ID: {aid} =====")
            self._log(f"URL: {url}")
            self._log(f"Прямой телефон: {direct_phone if direct_phone else 'Нет'}")
            
            result = self.fetch_phone(aid, url, direct_phone)
            processed_count += 1
            
            if result and "phone" in result and result["phone"]:
                self.parsed_data[aid] = {
                    "phone": result["phone"],
                    "notFormattedPhone": result.get("notFormattedPhone", re.sub(r'\D', '', result["phone"])),
                    "source": result.get("source", "browser"),
                    "method": result.get("method", "unknown")
                }
                success_count += 1
                self._log(f"✓ УСПЕХ: {result['phone']} (источник: {result.get('source')}, метод: {result.get('method')})")
            else:
                self.parsed_data[aid] = {
                    "phone": "не удалось получить",
                    "notFormattedPhone": "",
                    "source": "failed",
                    "method": "none"
                }
                self._log(f"✗ НЕУДАЧА: Не удалось получить номер для {aid}")
            
            # Сохраняем прогресс каждые 3 записи
            if processed_count % 3 == 0:
                self.save_data()
                self._log(f"Прогресс сохранен: {processed_count}/{self.max_phones}")
            
            # Пауза между запросами к сайту
            pause_time = 5  # 5 секунд между каждым запросом
            self._log(f"Пауза {pause_time} секунд перед следующим запросом...")
            time.sleep(pause_time)
            
            # Большая пауза каждые 10 запросов
            if processed_count % 10 == 0:
                big_pause = 60  # 1 минута каждые 10 запросов
                self._log(f"Выполнено {processed_count} запросов. Большая пауза {big_pause} секунд...")
                time.sleep(big_pause)
        
        self.save_data()
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        success_rate = (success_count / processed_count * 100) if processed_count > 0 else 0
        
        self._log("\n" + "="*60)
        self._log(f"ПАРСИНГ ЗАВЕРШЕН!")
        self._log(f"Время завершения: {end_time}")
        self._log(f"Общее время выполнения: {duration}")
        self._log(f"Обработано номеров: {processed_count}/{self.max_phones}")
        self._log(f"Успешных номеров: {success_count}/{processed_count}")
        self._log(f"Процент успеха: {success_rate:.1f}%")
        self._log(f"Режим: ТОЛЬКО браузер (API не использовался)")
        self._log("="*60 + "\n")
        
        self.export_phones_to_txt()