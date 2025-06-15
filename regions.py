import cianparser
import json

parser = cianparser.CianParser(location="Тюмень")

data = parser.get_flats(deal_type="sale", rooms=(1,2,3,4))


def save_data(data):
    """Сохраняет данные в JSON файл"""
    with open('regions.json', 'w', encoding='utf-8') as f:
        json.dump({"data": data}, f, ensure_ascii=False, indent=2)
    print(f"Данные сохранены. Всего номеров: {len(data)}")

save_data(data)