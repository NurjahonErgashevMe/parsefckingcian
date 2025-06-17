import cianparser
import json
from datetime import datetime
import utils
import requests
import re
import time
from bs4 import BeautifulSoup

def _log(log_callback, message):
    if log_callback:
        log_callback(message)
    else:
        print(message)

def get_block_id_and_phone(url, log_callback=None):
    """Извлекает blockId и/или телефон из HTML страницы объявления ТОЛЬКО ДЛЯ ЗАСТРОЙЩИКОВ"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text
        
        block_id = None
        phone = None
        
        # Пытаемся найти siteBlockId
        match = re.search(r'"siteBlockId":\s*(\d+)', html_content)
        if match:
            block_id = match.group(1)
            msg = f"Получен blockId: {block_id} для {url}"
            _log(log_callback, msg)
        else:
            msg = f"siteBlockId не найден на странице {url}"
            _log(log_callback, msg)
            
            # Если siteBlockId не найден, ищем offerPhone
            offer_match = re.search(r'"offerPhone":\s*"([^"]+)"', html_content)
            if offer_match:
                phone = offer_match.group(1)
                msg = f"Найден offerPhone: {phone} для {url}"
                _log(log_callback, msg)
        
        # Если еще не нашли телефон, пытаемся извлечь его напрямую из HTML
        if phone is None:
            soup = BeautifulSoup(html_content, 'html.parser')
            phone_element = soup.select_one('[data-testid="PhoneLink"], .phone-number')
            if phone_element:
                phone = phone_element.get_text(strip=True)
                # Очищаем номер от лишних символов
                phone = re.sub(r'[^\d+]', '', phone)
                msg = f"Найден прямой телефон: {phone} для {url}"
                _log(log_callback, msg)
        
        return block_id, phone
    
    except Exception as e:
        msg = f"Ошибка при получении данных: {str(e)}"
        _log(log_callback, msg)
        return None, None

def parse_cian_ads(log_callback=None):
    """Парсит объявления с CIAN и сохраняет в regions.json"""
    log_message = f"[{datetime.now()}] Начало парсинга объявлений..."
    _log(log_callback, log_message)
    utils.ensure_output_dir()
    
    try:
        # Создаем lock-файл
        utils.start_parsing()
        
        # Парсим данные БЕЗ дополнительных запросов
        parser = cianparser.CianParser(location="Тюмень")
        data = parser.get_flats(deal_type="sale", rooms=(1,2,3,4), additional_settings={"start_page":1, "end_page":1})
        
        # Проверяем и корректируем URL
        for item in data:
            if 'url' in item and not item['url'].startswith('http'):
                item['url'] = f"https://www.cian.ru{item['url']}"
        
        # Фильтруем ТОЛЬКО застройщиков
        developer_data = [item for item in data if item.get('author_type') == "developer"]
        
        # Получаем blockId и телефон ТОЛЬКО для застройщиков
        for item in developer_data:
            url = item.get('url')
            if url:
                block_id, phone = get_block_id_and_phone(url, log_callback)
                item['blockId'] = block_id
                item['directPhone'] = phone
                # Задержка, чтобы не нагружать сервер
                time.sleep(1.5)
            else:
                item['blockId'] = None
                item['directPhone'] = None
        
        # Сохраняем ВСЕ данные (но только застройщики имеют blockId и directPhone)
        region_file = utils.get_region_file()
        with open(region_file, 'w', encoding='utf-8') as f:
            json.dump({"data": data}, f, ensure_ascii=False, indent=2)
        
        log_message = f"[{datetime.now()}] Успешно! Сохранено {len(data)} объявлений ({len(developer_data)} от застройщиков) в {region_file}"
        _log(log_callback, log_message)
        
        return True, len(developer_data)
    
    except Exception as e:
        log_message = f"[{datetime.now()}] Ошибка парсинга: {str(e)}"
        _log(log_callback, log_message)
        return False, 0
    finally:
        # Всегда удаляем lock-файл
        utils.finish_parsing()