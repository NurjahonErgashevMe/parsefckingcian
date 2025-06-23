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

def get_block_id_and_phone(url, author_type, log_callback=None):
    """Извлекает blockId и/или телефон из HTML страницы объявления в зависимости от типа автора"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text
        
        block_id = None
        phone = None
        
        # ЛОГИКА В ЗАВИСИМОСТИ ОТ ТИПА АВТОРА
        if author_type == 'developer':
            # ДЛЯ ЗАСТРОЙЩИКОВ: ищем ТОЛЬКО siteBlockId
            match = re.search(r'"siteBlockId":\s*(\d+)', html_content)
            if match:
                block_id = match.group(1)
                msg = f"✅ Найден siteBlockId для застройщика: {block_id} для {url}"
                _log(log_callback, msg)
            else:
                msg = f"❌ siteBlockId НЕ найден для застройщика на странице {url}"
                _log(log_callback, msg)
        else:
            # ДЛЯ ОСТАЛЬНЫХ: ищем ТОЛЬКО offerPhone
            offer_match = re.search(r'"offerPhone":\s*"([^"]+)"', html_content)
            if offer_match:
                phone = offer_match.group(1)
                msg = f"✅ Найден готовый номер offerPhone: {phone} для {url}"
                _log(log_callback, msg)
            else:
                # Если offerPhone не найден, пытаемся извлечь его напрямую из HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                phone_element = soup.select_one('[data-testid="PhoneLink"], .phone-number')
                if phone_element:
                    phone = phone_element.get_text(strip=True)
                    # Очищаем номер от лишних символов
                    phone = re.sub(r'[^\d+]', '', phone)
                    msg = f"✅ Найден прямой телефон из HTML: {phone} для {url}"
                    _log(log_callback, msg)
                else:
                    msg = f"❌ offerPhone НЕ найден для НЕ-застройщика на странице {url}"
                    _log(log_callback, msg)
        
        return block_id, phone
    
    except Exception as e:
        msg = f"❌ Ошибка при получении данных: {str(e)}"
        _log(log_callback, msg)
        return None, None

def parse_cian_ads(log_callback=None):
    """Парсит объявления с CIAN и сохраняет в regions.json"""
    log_message = f"[{datetime.now()}] Начало парсинга объявлений..."
    _log(log_callback, log_message)
    utils.ensure_output_dir()
    
    try:
        # Проверяем возраст файла региона
        if utils.should_refresh_region_file():
            _log(log_callback, "⚠️ Данные региона устарели (>1 дня). Удаляем и обновляем...")
            utils.remove_region_file()
        
        # Создаем lock-файл
        utils.start_parsing()
        
        # Получаем регион из настроек
        region_name = utils.get_region_name()
        region_id = utils.get_region_id()
        rooms = utils.get_rooms()
        min_floor = utils.get_min_floor()
        max_floor = utils.get_max_floor()
        min_price = utils.get_min_price()
        max_price = utils.get_max_price()
        
        log_message = f"📍 Парсинг объявлений для региона: {region_name} (ID: {region_id})"
        _log(log_callback, log_message)
        log_message = f"🏠 Выбранные комнаты: {', '.join(map(str, rooms))}"
        _log(log_callback, log_message)
        
        if min_floor:
            _log(log_callback, f"⬇️ Мин. этаж: {min_floor}")
        if max_floor:
            _log(log_callback, f"⬆️ Макс. этаж: {max_floor}")
        if min_price:
            _log(log_callback, f"💰 Мин. цена: {min_price:,} ₽".replace(",", " "))
        if max_price:
            _log(log_callback, f"💰 Макс. цена: {max_price:,} ₽".replace(",", " "))
        
        # Формируем дополнительные настройки
        additional_settings = {
            "start_page": 1,
            "end_page": 1,
        }
        
        if min_floor:
            additional_settings["min_floor"] = min_floor
        if max_floor:
            additional_settings["max_floor"] = max_floor
        if min_price:
            additional_settings["min_price"] = min_price
        if max_price:
            additional_settings["max_price"] = max_price
        
        # Парсим данные
        parser = cianparser.CianParser(location=region_name)
        print(rooms , 'rooms')
        data = parser.get_flats(deal_type="sale", rooms=tuple(rooms), additional_settings=additional_settings)
        
        # Проверяем и корректируем URL
        for item in data:
            if 'url' in item and not item['url'].startswith('http'):
                item['url'] = f"https://www.cian.ru{item['url']}"
        
        # Получаем blockId и телефон для ВСЕХ объявлений В ЗАВИСИМОСТИ ОТ ТИПА АВТОРА
        for item in data:
            url = item.get('url')
            author_type = item.get('author_type')
            
            if url and author_type:
                block_id, phone = get_block_id_and_phone(url, author_type, log_callback)
                
                if author_type == 'developer':
                    # Для застройщиков сохраняем blockId, phone остается None
                    item['blockId'] = block_id
                    item['directPhone'] = None
                else:
                    # Для остальных сохраняем phone, blockId остается None
                    item['blockId'] = None
                    item['directPhone'] = phone
                
                # Задержка, чтобы не нагружать сервер
                time.sleep(1.5)
            else:
                item['blockId'] = None
                item['directPhone'] = None
        
        # Формируем данные для сохранения с метаданными
        result_data = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "region": {
                "name": region_name,
                "id": region_id
            },
            "rooms": rooms,
            "min_floor": min_floor,
            "max_floor": max_floor,
            "min_price": min_price,
            "max_price": max_price,
            "data": data
        }
        
        # Сохраняем ВСЕ данные
        region_file = utils.get_region_file()
        with open(region_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # Считаем статистику по типам авторов
        author_stats = {}
        phones_found = 0
        block_ids_found = 0
        
        for item in data:
            author_type = item.get('author_type', 'unknown')
            if author_type not in author_stats:
                author_stats[author_type] = {'total': 0, 'with_phone': 0, 'with_blockid': 0}
            
            author_stats[author_type]['total'] += 1
            
            if item.get('directPhone'):
                author_stats[author_type]['with_phone'] += 1
                phones_found += 1
            
            if item.get('blockId'):
                author_stats[author_type]['with_blockid'] += 1
                block_ids_found += 1
        
        # Логируем статистику
        log_message = f"[{datetime.now()}] Успешно! Сохранено {len(data)} объявлений в {region_file}"
        _log(log_callback, log_message)
        
        _log(log_callback, "\n📊 СТАТИСТИКА ПО ТИПАМ АВТОРОВ:")
        for author_type, stats in author_stats.items():
            if author_type == 'developer':
                _log(log_callback, f"  🏢 {author_type}: {stats['total']} объявлений, {stats['with_blockid']} с blockId (для API)")
            else:
                _log(log_callback, f"  👤 {author_type}: {stats['total']} объявлений, {stats['with_phone']} с готовыми телефонами")
        
        _log(log_callback, f"\n📞 Всего найдено готовых номеров (НЕ застройщики): {phones_found}")
        _log(log_callback, f"🔗 Всего найдено blockId (застройщики): {block_ids_found}")
        
        return True, len(data)
    
    except Exception as e:
        log_message = f"[{datetime.now()}] Ошибка парсинга: {str(e)}"
        _log(log_callback, log_message)
        return False, 0
    finally:
        # Всегда удаляем lock-файл
        utils.finish_parsing()