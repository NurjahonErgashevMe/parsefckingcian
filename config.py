import os

# Конфигурационные параметры
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Конфигурационные параметры
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
REGIONS_FILE = os.path.join(OUTPUT_DIR, "regions.json")
CODES_FILE = os.path.join(OUTPUT_DIR, "codes.txt")
PHONES_FILE = os.path.join(OUTPUT_DIR, "data.json")

# Параметры парсинга
LOCATION = "Тюмень"
DEAL_TYPE = "sale"
ROOMS = (1, 2, 3, 4)
DEFAULT_TYPE="developer"
MIN_PRICE = None
MAX_PRICE = None

# Настройки расписания
SCHEDULE_TIME = "00:00"  # Время запуска по МСК
REQUEST_DELAY = 15       # Пауза после 50 запросов (сек)
SAVE_INTERVAL = 5        # Сохранять каждые N номеров

# API параметры
API_URL = "https://api.cian.ru/newbuilding-dynamic-calltracking/v1/get-dynamic-phone"

# Значения будут перезаписаны при активации
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin": "https://tyumen.cian.ru",
    "Referer": "https://tyumen.cian.ru/",
    "Cookie": "default_cookie_value"  # Будет заменено при активации
}

PAYLOAD_TEMPLATE = {
    "blockId": 0,  # Будет заменено при активации
    "platformType": "webDesktop",
    "pageType": "offerCard",
    "placeType": "ContactsAside",
    "refererUrl": "",
    "analyticClientId": "G12.12321.123121D",  # Будет заменено при активации
    "utm": "default_utm_value"  # Будет заменено при активации
}

# Создаем директорию для данных
os.makedirs(OUTPUT_DIR, exist_ok=True)