import sqlite3
from contextlib import closing

DB_NAME = "cian_bot.db"

def init_db():
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        ''')
        # Устанавливаем регион по умолчанию (Тюмень)
        default_region = 'Тюмень'
        default_region_id = '4827'
        default_rooms = '1,2,3,4'  # Комнаты по умолчанию
        default_min_floor = ''  # Пустое значение = все этажи
        default_max_floor = ''  # Пустое значение = все этажи
        default_min_price = ''  # Пустое значение = нет ограничений
        default_max_price = ''  # Пустое значение = нет ограничений
        
        # Проверяем, есть ли уже настройки
        cursor.execute("SELECT value FROM settings WHERE key = 'region'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('region', default_region)
            )
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('region_id', default_region_id)
            )
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('rooms', default_rooms)
            )
            # Добавляем настройки этажей
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('min_floor', default_min_floor)
            )
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('max_floor', default_max_floor)
            )
            # Добавляем настройки цен
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('min_price', default_min_price)
            )
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('max_price', default_max_price)
            )
        conn.commit()

def get_setting(key, default=None):
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result[0] if result else default

def set_setting(key, value):
    with closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()

# Инициализация БД при импорте
init_db()