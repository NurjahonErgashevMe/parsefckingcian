import os

# Конфигурационные параметры
OUTPUT_DIR = "data"
REGIONS_FILE = os.path.join(OUTPUT_DIR, "regions.json")
CODES_FILE = os.path.join(OUTPUT_DIR, "codes.txt")
PHONES_FILE = os.path.join(OUTPUT_DIR, "data.json")

# Параметры парсинга
LOCATION = "Тюмень"
DEAL_TYPE = "sale"
ROOMS = (1, 2, 3, 4)

# Настройки расписания
SCHEDULE_TIME = "00:00"  # Время запуска по МСК
REQUEST_DELAY = 15       # Пауза после 50 запросов (сек)
SAVE_INTERVAL = 5        # Сохранять каждые N номеров

# API параметры
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

# Создаем директорию для данных
os.makedirs(OUTPUT_DIR, exist_ok=True)