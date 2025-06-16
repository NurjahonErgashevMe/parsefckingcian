import os

# Конфигурационные параметры
OUTPUT_DIR = "output"
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Origin" : "https://tyumen.cian.ru",
    "Referer" : "https://tyumen.cian.ru/",
    "Cookie" : "_CIAN_GK=98bd6c64-2384-4f1b-b232-caf1f0786683; _yasc=lljXOXxrpgyTQKg3VebP0vj1jwAmxj5lap/pEH9FH175//KY0I6iiDw0fVbBVZu1; uxfb_card_satisfaction=%5B307997699%5D; __zzatw-cian=MDA0dBA=Fz2+aQ==; _gcl_au=1.1.1521289697.1749983641; cookie_agreement_accepted=1; tmr_lvid=a3ba8c451eead70a57433bff3139ac21; tmr_lvidTS=1749983645104; cfidsw-cian=bwfMSNUQSMVrhQIN/WlAg9YnV5GUpuWFcmk6R9E2HAaUONF86KyRrJwZEGLoy2322vPo6/ybVw1gaadcPEnPGRvXMiF2GCbz818ObHDmJA5p+9pGVBKC+7HUUcAg3Q7e0k6frUi2BkqvkUn8kqMt0ig+H064hQq5WUzo; gsscw-cian=Lc4EIPWgdusU8DNCE+ghQnCSGjOAlAKeHQJzg+0XXJ6n1jzHX08/AavUrjZYEBirFgsneLXTtqVrtYsyMMUOxkKO+NY+/DM+oPsOuQyA9NHYDEPgxoq8s9YtwBryTnPKs9RcDR8aNmGMyFJ721sfAW3cxHWkkq0LG3V3hwHTFZ4TU8YtXoQ412yFuje6o0RANCqQz1vNrmrKSoO+vqVMGYOz0sLaPOog9WOUJJ7is2A8V7tW9BK/SU5IXF8udwacnWgGEvQ=; fgsscw-cian=OS8L87a1456ca5f794ff7f24c012599c7c2fcebb; sopr_utm=%7B%22utm_source%22%3A+%22direct%22%2C+%22utm_medium%22%3A+%22None%22%7D; sopr_session=ac1a55b45d034c49; _ga_3369S417EL=GS2.1.s1749983649$o1$g0$t1749983649$j60$l0$h0; _ga=GA1.1.74252020.1749983650; _ym_uid=1749983650675545562; _ym_d=1749983650; uxfb_usertype=searcher; _yasc=gd6KedRNlSKrRyHaSSNMXsQWiYnldtm1OqOOH8bVorIEu7tEVEj5Nt0pGR7j7uFN; _ym_visorc=b; _ym_isad=2; login_mro_popup=1; uxs_uid=49c46ef0-49d4-11f0-ba8f-03978a719378"
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