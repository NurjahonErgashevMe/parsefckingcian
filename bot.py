import os
import json
import time
import asyncio
import queue
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# Загрузка переменных окружения
load_dotenv()

# Импорт модулей парсера
import utils
import parser_ads
import phones_parser
import config
import cianparser

# Глобальные переменные для управления состоянием
parsing_in_progress = False
log_queue = queue.Queue()
current_log_message = None
scheduler = AsyncIOScheduler(timezone=pytz.timezone('Europe/Moscow'))
bot_task = None  # Для хранения задачи бота

# Инициализация бота
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()

# Callback data для кнопок
class AuthorTypeCallback(CallbackData, prefix="author"):
    type: str

# Состояния для FSM
class RegionState(StatesGroup):
    waiting_region_name = State()

class RoomState(StatesGroup):
    selecting_rooms = State()

class MinFloorState(StatesGroup):
    selecting_range = State()
    selecting_floors = State()

class MaxFloorState(StatesGroup):
    selecting_range = State()
    selecting_floors = State()

class PriceState(StatesGroup):
    min_price = State()
    max_price = State()

async def delete_file_after_delay(file_path: str, delay_seconds: int = 10):
    """Удаляет файл через указанное количество секунд"""
    try:
        await asyncio.sleep(delay_seconds)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Файл {file_path} автоматически удален через {delay_seconds} секунд")
        else:
            print(f"⚠️ Файл {file_path} уже не существует")
    except Exception as e:
        print(f"❌ Ошибка при удалении файла {file_path}: {str(e)}")

async def update_log_message(chat_id: int):
    """Обновляет сообщение с логами в телеграме"""
    global current_log_message, log_queue
    
    # Собираем все логи из очереди
    logs = []
    while not log_queue.empty():
        logs.append(log_queue.get())
    
    if not logs:
        return
    
    log_text = "\n".join(logs)
    
    try:
        if current_log_message:
            # Получаем текущий текст сообщения
            current_text = current_log_message.text
            
            # Объединяем с новыми логами
            new_text = f"{current_text}\n{log_text}"
            
            # Обрезаем до 4096 символов
            if len(new_text) > 4096:
                new_text = new_text[-4096:]
            
            # Редактируем существующее сообщение
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=current_log_message.message_id,
                text=new_text
            )
        else:
            # Создаем новое сообщение
            new_text = log_text[-4096:] if len(log_text) > 4096 else log_text
            message = await bot.send_message(chat_id, new_text)
            current_log_message = message
    except Exception as e:
        print(f"Ошибка при обновлении логов: {e}")

def log_callback(message: str):
    """Callback для записи логов в очередь"""
    log_queue.put(message)

def run_parser(author_type=None, is_scheduled=False):
    """Запускает парсер в отдельном потоке"""
    global parsing_in_progress
    
    try:
        utils.ensure_output_dir()
        region_file = utils.get_region_file()
        
        log_callback("\n" + "="*50)
        log_callback(f"CIAN Parser запущен: {datetime.now()}")
        
        # Определяем название типа автора для логов
        author_names = {
            'developer': '🏗️ застройщики',
            'real_estate_agent': '🏢 агенства недвижимостей',
            'homeowner': '🏠 владельцы домов',
            'realtor': '👔 риэлторы'
        }
        author_display = author_names.get(author_type, '👥 все типы')
        log_callback(f"🎯 Тип авторов: {author_display}")
        
        if is_scheduled:
            log_callback("⏰ АВТОМАТИЧЕСКИЙ ПАРСИНГ ПО РАСПИСАНИЮ")
            
        log_callback("="*50)
        
        # Проверяем наличие файла с данными
        if os.path.exists(region_file):
            try:
                with open(region_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if "data" in data and len(data["data"]) > 0:
                    log_callback(f"Найдено {len(data['data'])} объявлений. Начинаем парсинг телефонов...")
                    # Передаем флаг очистки файлов и тип автора
                    parser = phones_parser.CianPhoneParser(
                        log_callback=log_callback,
                        clear_existing=True,
                        author_type=author_type,
                        is_scheduled=is_scheduled
                    )
                    return parser.parse()
                    
            except (json.JSONDecodeError, KeyError) as e:
                log_callback(f"Ошибка чтения файла регионов: {str(e)}. Будет выполнен перепарсинг.")
        
        log_callback("Файл с объявлениями отсутствует или пуст.")
        
        if utils.is_parsing_in_progress():
            log_callback("Парсинг объявлений уже выполняется. Ожидание завершения...")
            
            while utils.is_parsing_in_progress():
                time.sleep(30)
                log_callback("Ожидание...")
            
            log_callback("Парсинг объявлений завершен! Начинаем парсинг телефонов...")
            # Передаем флаг очистки файлов и тип автора
            parser = phones_parser.CianPhoneParser(
                log_callback=log_callback,
                clear_existing=True,
                author_type=author_type,
                is_scheduled=is_scheduled
            )
            return parser.parse()
        else:
            log_callback("Запускаем парсинг объявлений...")
            if parser_ads.parse_cian_ads(log_callback=log_callback):
                log_callback("Начинаем парсинг телефонов...")
                # Передаем флаг очистки файлов и тип автора
                parser = phones_parser.CianPhoneParser(
                    log_callback=log_callback,
                    clear_existing=True,
                    author_type=author_type,
                    is_scheduled=is_scheduled
                )
                return parser.parse()
    
    except Exception as e:
        log_callback(f"❌ Критическая ошибка при парсинге: {str(e)}")
        return None
    finally:
        parsing_in_progress = False

def create_author_type_keyboard():
    """Создает клавиатуру для выбора типа автора"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🏢 Агенства недвижимостей",
                callback_data=AuthorTypeCallback(type="real_estate_agent").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Владельцы домов",
                callback_data=AuthorTypeCallback(type="homeowner").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="👔 Риэлторы",
                callback_data=AuthorTypeCallback(type="realtor").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Парсинг завершен",
                callback_data=AuthorTypeCallback(type="done").pack()
            )
        ]
    ])
    return keyboard

def create_main_keyboard():
    """Создает главную клавиатуру меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Парсить")],
            [KeyboardButton(text="⚙️ Настройки парсинга")]
        ],
        resize_keyboard=True
    )

def generate_regions_file():
    """Генерирует файл со списком доступных регионов"""
    regions = cianparser.list_locations()
    
    # Сортируем регионы по алфавиту
    regions.sort(key=lambda x: x[0].lower())
    
    # Создаем временный файл
    filename = "available_regions.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("Список доступных регионов для парсинга:\n")
        f.write("=" * 50 + "\n\n")
        
        for region in regions:
            f.write(f"• {region[0]} (ID: {region[1]})\n")
    
    return filename

def create_rooms_keyboard(selected_rooms):
    """Создает клавиатуру для выбора комнат"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Создаем кнопки для каждой комнаты
    buttons_row = []
    for room in range(1, 7):
        # Добавляем галочку, если комната выбрана
        emoji = "✅" if room in selected_rooms else ""
        buttons_row.append(
            InlineKeyboardButton(
                text=f"{room} {emoji}",
                callback_data=f"room_{room}"
            )
        )
        
        # Каждые 3 кнопки начинаем новую строку
        if len(buttons_row) == 3:
            keyboard.inline_keyboard.append(buttons_row)
            buttons_row = []
    
    # Добавляем оставшиеся кнопки
    if buttons_row:
        keyboard.inline_keyboard.append(buttons_row)
    
    # Кнопка сохранения
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="💾 Сохранить настройки", callback_data="save_rooms")
    ])
    
    return keyboard

def create_floor_range_keyboard(min_value=0):
    """Клавиатура с диапазонами этажей с фильтрацией"""
    ranges = [
        ("1-10", 1, 10),
        ("11-20", 11, 20),
        ("21-30", 21, 30),
        ("31-40", 31, 40),
        ("41-50", 41, 50),
        ("51-60", 51, 60),
        ("61-70", 61, 70),
        ("71-80", 71, 80),
        ("81-90", 81, 90),
        ("91-100", 91, 100),
        ("Все этажи", 0, 0)
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    
    for name, start, end in ranges:
        # Фильтруем диапазоны: показываем только те, где верхняя граница >= min_value
        if min_value > 0 and end < min_value and name != "Все этажи":
            continue
            
        if name == "Все этажи":
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=name, callback_data=f"floor_range_all")
            ])
        else:
            row.append(InlineKeyboardButton(text=name, callback_data=f"floor_range_{start}_{end}"))
            if len(row) == 3:
                keyboard.inline_keyboard.append(row)
                row = []
    
    if row:
        keyboard.inline_keyboard.append(row)
    
    return keyboard

def create_floor_selection_keyboard(start, end, selected_floors, min_value=0):
    """Клавиатура для выбора конкретных этажей с фильтрацией"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    
    # Если выбран диапазон "Все этажи"
    if start == 0 and end == 0:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="✅ Все этажи выбраны", callback_data="floor_none")
        ])
    else:
        for floor in range(start, end + 1):
            # Пропускаем этажи меньше минимального значения
            if min_value > 0 and floor < min_value:
                continue
                
            emoji = "✅" if floor in selected_floors else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{floor}{emoji}",
                    callback_data=f"floor_{floor}"
                )
            )
            if len(row) == 5:
                keyboard.inline_keyboard.append(row)
                row = []
    
    if row:
        keyboard.inline_keyboard.append(row)
    
    # Кнопки управления
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="✅ Выбрать все в диапазоне",
            callback_data="floor_select_all"
        )
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="💾 Сохранить выбор",
            callback_data="floor_save"
        )
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Назад к диапазонам",
            callback_data="floor_back"
        )
    ])
    
    return keyboard

def create_price_keyboard():
    """Создает клавиатуру для настроек цен"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬇️ Минимальная цена", callback_data="min_price_set")
        ],
        [
            InlineKeyboardButton(text="⬆️ Максимальная цена", callback_data="max_price_set")
        ],
        [
            InlineKeyboardButton(text="❌ Очистить цены", callback_data="clear_prices")
        ],
        [
            InlineKeyboardButton(text="💾 Сохранить настройки", callback_data="save_prices")
        ]
    ])

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я бот для парсинга телефонных номеров с CIAN.\n\n"
        "🎯 Бот умеет парсить номера от разных типов авторов:\n"
        "• 🏗️ Застройщики\n"
        "• 🏢 Агенства недвижимостей\n"
        "• 🏠 Владельцы домов\n"
        "• 👔 Риэлторы\n\n"
        "Нажми кнопку '🚀 Парсить' или отправь команду /parse, чтобы начать сбор данных.",
        reply_markup=create_main_keyboard()
    )

@dp.message(Command("parse"))
@dp.message(lambda message: message.text == "🚀 Парсить")
async def parse_command(message: types.Message):
    """Обработчик команды /parse - начинает с застройщиков"""
    global parsing_in_progress, current_log_message
    
    if parsing_in_progress:
        await message.answer("⚠️ Парсинг уже запущен! Дождитесь завершения.")
        return
    
    # Сбрасываем состояние логов
    current_log_message = None
    while not log_queue.empty():
        log_queue.get()
    
    parsing_in_progress = True
    log_callback("⏳ Подготовка к парсингу застройщиков...")
    
    # Запускаем парсинг застройщиков в отдельном потоке
    threading.Thread(target=run_parser, args=(config.DEFAULT_TYPE,), daemon=True).start()
    
    # Запускаем задачу для периодического обновления логов
    asyncio.create_task(log_updater(message.chat.id))

@dp.message(F.text == "⚙️ Настройки парсинга")
async def parsing_settings(message: types.Message):
    """Обработчик кнопки настроек парсинга"""
    current_region = utils.get_region_name()
    region_id = utils.get_region_id()
    current_rooms = utils.get_rooms()
    current_min_floor = utils.get_min_floor()
    current_max_floor = utils.get_max_floor()
    current_min_price = utils.get_min_price()
    current_max_price = utils.get_max_price()
    auto_parse_enabled = utils.get_setting('auto_parse_enabled', '0') == '1'
    
    # Получаем информацию о файле региона
    region_info = utils.get_region_info()
    
    # Форматируем информацию о дате создания
    created_at_info = ""
    if region_info and region_info.get("created_at"):
        try:
            # Удаляем 'Z' в конце строки и парсим
            created_at_str = region_info["created_at"].rstrip('Z')
            created_at = datetime.fromisoformat(created_at_str)
            created_at_info = f"• <b>Дата создания:</b> {created_at.strftime('%d.%m.%Y %H:%M')}\n"
        except ValueError:
            created_at_info = f"• <b>Дата создания:</b> {region_info['created_at']}\n"
    
    # Форматируем этажи
    min_floor_text = "не задано" if not current_min_floor else ", ".join(map(str, current_min_floor))
    max_floor_text = "не задано" if not current_max_floor else ", ".join(map(str, current_max_floor))
    
    # Форматируем цены
    min_price_text = "не задано" if not current_min_price else f"{current_min_price:,} ₽".replace(",", " ")
    max_price_text = "не задано" if not current_max_price else f"{current_max_price:,} ₽".replace(",", " ")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Изменить регион")],
            [KeyboardButton(text="Список регионов")],
            [KeyboardButton(text="Выбрать комнаты")],
            [KeyboardButton(text="Настроить этажи")],
            [KeyboardButton(text="Настроить цены")],
            [KeyboardButton(text="Автопарсинг")],
            [KeyboardButton(text="Сбросить настройки")],
            [KeyboardButton(text="Назад в меню")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"⚙️ <b>Текущие настройки парсинга:</b>\n"
        f"• <b>Регион:</b> {current_region}\n"
        f"• <b>ID региона:</b> {region_id}\n"
        f"• <b>Комнаты:</b> {', '.join(map(str, current_rooms))}\n"
        f"• <b>Мин. этаж:</b> {min_floor_text}\n"
        f"• <b>Макс. этаж:</b> {max_floor_text}\n"
        f"• <b>Мин. цена:</b> {min_price_text}\n"
        f"• <b>Макс. цена:</b> {max_price_text}\n"
        f"• <b>Автопарсинг:</b> {'✅ включен' if auto_parse_enabled else '❌ выключен'}\n"
        f"{created_at_info}\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.message(F.text == "Автопарсинг")
async def auto_parse_settings(message: types.Message):
    """Настройки автоматического парсинга"""
    auto_parse_enabled = utils.get_setting('auto_parse_enabled', '0') == '1'
    schedule_time = utils.get_setting('schedule_time', config.SCHEDULE_TIME)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🟢 Включить" if not auto_parse_enabled else "🔴 Выключить",
                callback_data=f"toggle_auto_parse_{int(not auto_parse_enabled)}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🕒 Изменить время",
                callback_data="change_schedule_time"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="back_to_settings"
            )
        ]
    ])
    
    await message.answer(
        f"⏰ <b>Настройки автоматического парсинга:</b>\n"
        f"• Статус: {'🟢 включен' if auto_parse_enabled else '🔴 выключен'}\n"
        f"• Время запуска: {schedule_time}\n\n"
        f"Автопарсинг выполняется ежедневно в указанное время.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("toggle_auto_parse_"))
async def toggle_auto_parse(callback: types.CallbackQuery):
    """Включение/выключение автоматического парсинга"""
    new_state = callback.data.split("_")[-1]
    utils.set_setting('auto_parse_enabled', new_state)
    
    if new_state == '1':
        await callback.answer("✅ Автопарсинг включен!")
    else:
        await callback.answer("❌ Автопарсинг выключен!")
    
    await auto_parse_settings(callback.message)

@dp.callback_query(F.data == "change_schedule_time")
async def change_schedule_time(callback: types.CallbackQuery, state: FSMContext):
    """Изменение времени автоматического парсинга"""
    await callback.message.answer(
        "🕒 Введите новое время для автоматического парсинга в формате ЧЧ:ММ (например, 03:00):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state("waiting_schedule_time")

@dp.message(F.text.regexp(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'), StateFilter("waiting_schedule_time"))
async def process_schedule_time(message: types.Message, state: FSMContext):
    """Обработка нового времени для расписания"""
    new_time = message.text.strip()
    utils.set_setting('schedule_time', new_time)
    
    # Обновляем задачу в планировщике
    scheduler.remove_all_jobs()
    schedule_daily_parse()
    
    await message.answer(f"✅ Время автоматического парсинга установлено на {new_time}")
    await state.clear()
    await auto_parse_settings(message)

@dp.message(StateFilter("waiting_schedule_time"))
async def invalid_schedule_time(message: types.Message):
    """Обработка неверного формата времени"""
    await message.answer("❌ Неверный формат времени. Используйте формат ЧЧ:ММ (например, 03:00)")

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings_from_auto(callback: types.CallbackQuery):
    """Возврат в настройки"""
    await parsing_settings(callback.message)

@dp.message(F.text == "Изменить регион")
async def change_region(message: types.Message, state: FSMContext):
    """Обработчик кнопки изменения региона"""
    await state.set_state(RegionState.waiting_region_name)
    
    # Отправляем подсказку с популярными регионами
    popular_regions = [
        "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
        "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону"
    ]
    
    regions_text = "\n".join([f"• {region}" for region in popular_regions])
    
    await message.answer(
        "Введите название региона:\n\n"
        "🔹 <b>Популярные регионы:</b>\n"
        f"{regions_text}\n\n"
        "Для полного списка регионов нажмите кнопку 'Список регионов'",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )

@dp.message(F.text == "Список регионов")
async def send_regions_list(message: types.Message):
    """Отправляет список доступных регионов в виде файла"""
    try:
        # Генерируем файл со списком регионов
        regions_file = generate_regions_file()
        file = FSInputFile(regions_file)
        
        # Отправляем файл
        await message.answer_document(
            document=file,
            caption="📋 <b>Полный список доступных регионов:</b>\n\n"
                    "Используйте точное название региона при вводе.",
            parse_mode="HTML"
        )
        
        # Удаляем файл через 30 секунд
        asyncio.create_task(delete_file_after_delay(regions_file, 30))
        
        # Предлагаем ввести регион
        await message.answer(
            "Введите название региона:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Назад в настройки")]],
                resize_keyboard=True
            )
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось сгенерировать список регионов: {str(e)}")

@dp.message(F.text == "Выбрать комнаты")
async def select_rooms(message: types.Message, state: FSMContext):
    """Обработчик кнопки выбора комнат"""
    current_rooms = utils.get_rooms()
    keyboard = create_rooms_keyboard(current_rooms)
    
    await message.answer(
        "Выберите количество комнат для парсинга:\n\n"
        "Нажмите на комнату, чтобы добавить/удалить её из выборки. "
        "Значок ✅ означает, что комната выбрана.\n\n"
        "После выбора нажмите '💾 Сохранить настройки'.",
        reply_markup=keyboard
    )
    
    # Сохраняем текущий выбор в состояние
    await state.set_data({"selected_rooms": current_rooms})
    await state.set_state(RoomState.selecting_rooms)

@dp.message(F.text == "Настроить этажи")
async def setup_floors(message: types.Message, state: FSMContext):
    """Запуск настройки этажей"""
    await state.set_state(MinFloorState.selecting_range)
    await message.answer(
        "Выберите диапазон для МИНИМАЛЬНОГО этажа:",
        reply_markup=create_floor_range_keyboard()
    )

@dp.message(F.text == "Настроить цены")
async def setup_prices(message: types.Message, state: FSMContext):
    """Запуск настройки цен"""
    current_min_price = utils.get_min_price()
    current_max_price = utils.get_max_price()
    
    min_price_text = "не задано" if not current_min_price else f"{current_min_price:,} ₽".replace(",", " ")
    max_price_text = "не задано" if not current_max_price else f"{current_max_price:,} ₽".replace(",", " ")
    
    await message.answer(
        f"💰 <b>Текущие настройки цен:</b>\n"
        f"• Минимальная цена: {min_price_text}\n"
        f"• Максимальная цена: {max_price_text}\n\n"
        "Выберите действие:",
        reply_markup=create_price_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "min_price_set")
async def set_min_price(callback: types.CallbackQuery, state: FSMContext):
    """Запрос минимальной цены"""
    await callback.message.edit_text(
        "⬇️ Введите минимальную цену в рублях (например: 5000000):\n\n"
        "Цена должна быть целым числом без пробелов и других символов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Без ограничений", callback_data="min_price_clear")
        ]])
    )
    await state.set_state(PriceState.min_price)

@dp.callback_query(F.data == "max_price_set")
async def set_max_price(callback: types.CallbackQuery, state: FSMContext):
    """Запрос максимальной цены"""
    await callback.message.edit_text(
        "⬆️ Введите максимальную цену в рублях (например: 10000000):\n\n"
        "Цена должна быть целым числом без пробелов и других символов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Без ограничений", callback_data="max_price_clear")
        ]])
    )
    await state.set_state(PriceState.max_price)

@dp.callback_query(F.data.startswith(("min_price_clear", "max_price_clear")))
async def clear_price(callback: types.CallbackQuery, state: FSMContext):
    """Очистка цены"""
    price_type = "min_price" if callback.data.startswith("min_price") else "max_price"
    
    if price_type == "min_price":
        utils.set_min_price(None)
    else:
        utils.set_max_price(None)
    
    await callback.answer(f"✅ {price_type.replace('_', ' ').capitalize()} очищена")
    await setup_prices(callback.message, state)

@dp.message(PriceState.min_price, F.text)
async def process_min_price(message: types.Message, state: FSMContext):
    """Обработка минимальной цены"""
    if message.text == "❌ Без ограничений":
        utils.set_min_price(None)
        await message.answer("✅ Минимальная цена очищена")
    else:
        try:
            price = int(message.text)
            utils.set_min_price(price)
            await message.answer(f"✅ Минимальная цена установлена: {price:,} ₽".replace(",", " "))
        except ValueError:
            await message.answer("❌ Неверный формат цены. Введите целое число (например: 5000000)")
    
    await state.clear()
    await setup_prices(message, state)

@dp.message(PriceState.max_price, F.text)
async def process_max_price(message: types.Message, state: FSMContext):
    """Обработка максимальной цены"""
    if message.text == "❌ Без ограничений":
        utils.set_max_price(None)
        await message.answer("✅ Максимальная цена очищена")
    else:
        try:
            price = int(message.text)
            utils.set_max_price(price)
            await message.answer(f"✅ Максимальная цена установлена: {price:,} ₽".replace(",", " "))
        except ValueError:
            await message.answer("❌ Неверный формат цены. Введите целое число (например: 10000000)")
    
    await state.clear()
    await setup_prices(message, state)

@dp.callback_query(F.data == "clear_prices")
async def clear_all_prices(callback: types.CallbackQuery, state: FSMContext):
    """Очистка всех цен"""
    utils.set_min_price(None)
    utils.set_max_price(None)
    await callback.answer("✅ Все цены очищены")
    await setup_prices(callback.message, state)

@dp.callback_query(F.data == "save_prices")
async def save_prices(callback: types.CallbackQuery, state: FSMContext):
    """Сохранение настроек цен"""
    await callback.answer("✅ Настройки цен сохранены!")
    await parsing_settings(callback.message)

@dp.message(F.text == "Сбросить настройки")
async def reset_settings(message: types.Message):
    """Сброс всех настроек к значениям по умолчанию"""
    # Сбрасываем настройки
    utils.reset_settings()
    
    await message.answer(
        "✅ Все настройки сброшены к значениям по умолчанию:\n"
        "• Регион: Тюмень\n"
        "• Комнаты: 1, 2, 3, 4\n"
        "• Минимальный этаж: не задано\n"
        "• Максимальный этаж: не задано\n"
        "• Минимальная цена: не задано\n"
        "• Максимальная цена: не задано\n"
        "• Автопарсинг: ❌ выключен",
        reply_markup=create_main_keyboard()
    )

@dp.callback_query(RoomState.selecting_rooms, F.data.startswith("room_"))
async def toggle_room(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик переключения комнаты"""
    room_num = int(callback.data.split("_")[1])
    state_data = await state.get_data()
    selected_rooms = state_data.get("selected_rooms", [])
    
    if room_num in selected_rooms:
        selected_rooms.remove(room_num)
    else:
        selected_rooms.append(room_num)
        selected_rooms.sort()
    
    # Обновляем состояние
    await state.update_data(selected_rooms=selected_rooms)
    
    # Обновляем клавиатуру
    keyboard = create_rooms_keyboard(selected_rooms)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(RoomState.selecting_rooms, F.data == "save_rooms")
async def save_rooms(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик сохранения выбранных комнат"""
    state_data = await state.get_data()
    selected_rooms = state_data.get("selected_rooms", [])
    
    # Сохраняем настройки
    utils.set_rooms(selected_rooms)
    
    await callback.answer("✅ Настройки комнат сохранены!")
    await callback.message.delete()
    await state.clear()
    
    # Возвращаем в меню настроек
    await parsing_settings(callback.message)

@dp.callback_query(MinFloorState.selecting_range, F.data.startswith("floor_range_"))
async def min_floor_range_selected(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    if data[2] == "all":
        await state.update_data(range_start=0, range_end=0, range_name="Все этажи")
        utils.set_min_floor([])
        await callback.answer("Минимальный этаж: без ограничений")
        await state.set_state(MaxFloorState.selecting_range)
        await callback.message.answer(
            "Выберите диапазон для МАКСИМАЛЬНОГО этажа:",
            reply_markup=create_floor_range_keyboard()
        )
        return
    else:
        start = int(data[2])
        end = int(data[3])
        await state.update_data(range_start=start, range_end=end, range_name=f"{start}-{end}")
    
    await state.set_state(MinFloorState.selecting_floors)
    current_floors = utils.get_min_floor()
    
    state_data = await state.get_data()
    await callback.message.edit_text(
        f"Выберите МИНИМАЛЬНЫЕ этажи в диапазоне {state_data['range_name']}:\n"
        "(Нажмите на этаж, чтобы выбрать/отменить)",
        reply_markup=create_floor_selection_keyboard(
            state_data['range_start'],
            state_data['range_end'],
            current_floors
        )
    )

@dp.callback_query(MinFloorState.selecting_floors, F.data.startswith("floor_"))
async def min_floor_selected(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    action = data_parts[1]
    state_data = await state.get_data()
    current_floors = utils.get_min_floor()
    
    if action == "select":  # Выбрать все
        new_floors = list(range(state_data['range_start'], state_data['range_end'] + 1))
        utils.set_min_floor(new_floors)
        await callback.answer("Все этажи в диапазоне выбраны!")
    elif action == "save":  # Сохранить
        # Сохраняем минимальные этажи
        current_min_floors = utils.get_min_floor()
        
        # Вычисляем минимальное значение для максимального этажа
        min_value_for_max = max(current_min_floors) if current_min_floors else 0
        
        await callback.answer("Выбор сохранён")
        await state.set_state(MaxFloorState.selecting_range)
        await callback.message.answer(
            "Выберите диапазон для МАКСИМАЛЬНОГО этажа:",
            reply_markup=create_floor_range_keyboard(min_value=min_value_for_max)
        )
        return
    elif action == "back":  # Назад
        await state.set_state(MinFloorState.selecting_range)
        await callback.message.edit_text(
            "Выберите диапазон для МИНИМАЛЬНОГО этажа:",
            reply_markup=create_floor_range_keyboard()
        )
        return
    else:  # Выбор конкретного этажа
        floor = int(action)
        if floor in current_floors:
            current_floors.remove(floor)
        else:
            current_floors.append(floor)
        utils.set_min_floor(current_floors)
    
    # Обновляем клавиатуру
    await callback.message.edit_reply_markup(
        reply_markup=create_floor_selection_keyboard(
            state_data['range_start'],
            state_data['range_end'],
            utils.get_min_floor()
        )
    )
    await callback.answer()

@dp.callback_query(MaxFloorState.selecting_range, F.data.startswith("floor_range_"))
async def max_floor_range_selected(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    state_data = await state.get_data()
    current_min_floors = utils.get_min_floor()
    min_value_for_max = max(current_min_floors) if current_min_floors else 0
    
    if data[2] == "all":
        await state.update_data(range_start=0, range_end=0, range_name="Все этажи")
        utils.set_max_floor([])
        await callback.answer("Максимальный этаж: без ограничений")
        await save_floors_settings(callback.message, state)
        return
    else:
        start = int(data[2])
        end = int(data[3])
        await state.update_data(range_start=start, range_end=end, range_name=f"{start}-{end}")
    
    await state.set_state(MaxFloorState.selecting_floors)
    current_floors = utils.get_max_floor()
    
    state_data = await state.get_data()
    await callback.message.edit_text(
        f"Выберите МАКСИМАЛЬНЫЕ этажи в диапазоне {state_data['range_name']}:\n"
        "(Нажмите на этаж, чтобы выбрать/отменить)",
        reply_markup=create_floor_selection_keyboard(
            state_data['range_start'],
            state_data['range_end'],
            current_floors,
            min_value=min_value_for_max
        )
    )

@dp.callback_query(MaxFloorState.selecting_floors, F.data.startswith("floor_"))
async def max_floor_selected(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    action = data_parts[1]
    state_data = await state.get_data()
    current_floors = utils.get_max_floor()
    current_min_floors = utils.get_min_floor()
    min_value_for_max = max(current_min_floors) if current_min_floors else 0
    
    if action == "select":  # Выбрать все
        # Фильтруем этажи по минимальному значению
        new_floors = [
            f for f in range(state_data['range_start'], state_data['range_end'] + 1) 
            if f >= min_value_for_max
        ]
        utils.set_max_floor(new_floors)
        await callback.answer("Все этажи в диапазоне выбраны!")
    elif action == "save":  # Сохранить
        await save_floors_settings(callback.message, state)
        return
    elif action == "back":  # Назад
        await state.set_state(MaxFloorState.selecting_range)
        await callback.message.edit_text(
            "Выберите диапазон для МАКСИМАЛЬНОГО этажа:",
            reply_markup=create_floor_range_keyboard(min_value=min_value_for_max)
        )
        return
    else:  # Выбор конкретного этажа
        floor = int(action)
        # Проверяем, что этаж не меньше минимального значения
        if min_value_for_max > 0 and floor < min_value_for_max:
            await callback.answer("Этаж должен быть больше минимального значения!")
            return
            
        if floor in current_floors:
            current_floors.remove(floor)
        else:
            current_floors.append(floor)
        utils.set_max_floor(current_floors)
    
    # Обновляем клавиатуру
    await callback.message.edit_reply_markup(
        reply_markup=create_floor_selection_keyboard(
            state_data['range_start'],
            state_data['range_end'],
            utils.get_max_floor(),
            min_value=min_value_for_max
        )
    )
    await callback.answer()

async def save_floors_settings(message: types.Message, state: FSMContext):
    """Сохранение настроек этажей и завершение"""
    min_floors = utils.get_min_floor()
    max_floors = utils.get_max_floor()
    
    min_text = "не задано" if not min_floors else ", ".join(map(str, min_floors))
    max_text = "не задано" if not max_floors else ", ".join(map(str, max_floors))
    
    await state.clear()
    await message.answer(
        f"✅ Настройки этажей сохранены:\n"
        f"• Минимальный этаж: {min_text}\n"
        f"• Максимальный этаж: {max_text}\n\n"
        "Старые данные парсинга удалены.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Назад в настройки")]],
            resize_keyboard=True
        )
    )

@dp.message(RegionState.waiting_region_name)
async def process_region_name(message: types.Message, state: FSMContext):
    """Обработчик ввода названия региона"""
    # Проверяем, если пользователь хочет вернутьс
    if message.text == "Назад в настройки":
        await state.clear()
        await parsing_settings(message)
        return
        
    region_name = message.text.strip()
    locations = cianparser.list_locations()
    
    # Ищем точное совпадение
    found = None
    for loc in locations:
        if loc[0].lower() == region_name.lower():
            found = loc
            break
    
    if found:
        region_id = found[1]
        utils.set_region(region_name, region_id)
        await state.clear()
        
        await message.answer(
            f"✅ <b>Регион изменен</b>\n"
            f"• <b>Новый регион:</b> {region_name}\n"
            f"• <b>ID региона:</b> {region_id}\n\n"
            f"Теперь все парсинги будут выполняться для этого региона.",
            reply_markup=create_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        # Попробуем найти похожие
        similar = []
        for loc in locations:
            if region_name.lower() in loc[0].lower():
                similar.append(loc[0])
                if len(similar) >= 5:  # Ограничим 5 вариантами
                    break
        
        if similar:
            suggestions = "\n".join([f"• {name}" for name in similar])
            await message.answer(
                f"❌ <b>Регион не найден</b>\n\n"
                f"Возможно вы имели в виду:\n"
                f"{suggestions}\n\n"
                "Пожалуйста, введите название точно:",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ Регион не найден. Пожалуйста, введите название точно:"
            )

@dp.message(F.text == "Назад в меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    """Обработчик кнопки возврата в меню"""
    await state.clear()
    await message.answer(
        "Главное меню:",
        reply_markup=create_main_keyboard()
    )

@dp.message(F.text == "Назад в настройки")
async def back_to_settings(message: types.Message, state: FSMContext):
    """Обработчик кнопки возврата в настройки"""
    await state.clear()
    await parsing_settings(message)

@dp.callback_query(AuthorTypeCallback.filter())
async def handle_author_type_selection(callback: types.CallbackQuery, callback_data: AuthorTypeCallback):
    """Обработчик выбора типа автора"""
    global parsing_in_progress, current_log_message
    
    await callback.answer()
    
    if callback_data.type == "done":
        await callback.message.edit_text(
            "✅ Парсинг полностью завершен!\n\n"
            "Спасибо за использование бота! 🎉\n"
            "Чтобы начать новый парсинг, используйте команду /parse"
        )
        return
    
    if parsing_in_progress:
        await callback.message.answer("⚠️ Парсинг уже запущен! Дождитесь завершения.")
        return
    
    # Определяем название типа автора
    author_names = {
        'real_estate_agent': '🏢 агенства недвижимостей',
        'homeowner': '🏠 владельцы домов',
        'realtor': '👔 риэлторы'
    }
    author_display = author_names.get(callback_data.type, callback_data.type)
    
    # Сбрасываем состояние логов
    current_log_message = None
    while not log_queue.empty():
        log_queue.get()
    
    parsing_in_progress = True
    log_callback(f"⏳ Подготовка к парсингу: {author_display}...")
    
    # Обновляем сообщение
    await callback.message.edit_text(
        f"🚀 Запущен парсинг: {author_display}\n\n"
        "Ожидайте результатов..."
    )
    
    # Запускаем парсинг выбранного типа в отдельном потоке
    threading.Thread(target=run_parser, args=(callback_data.type,), daemon=True).start()
    
    # Запускаем задачу для периодического обновления логов
    asyncio.create_task(log_updater(callback.message.chat.id))

def schedule_daily_parse():
    """Настраивает ежедневный парсинг по расписанию"""
    schedule_time = utils.get_setting('schedule_time', config.SCHEDULE_TIME)
    auto_parse_enabled = utils.get_setting('auto_parse_enabled', '0') == '1'
    
    if not auto_parse_enabled:
        return
    
    try:
        hour, minute = map(int, schedule_time.split(':'))
        scheduler.add_job(
            run_scheduled_parse,
            'cron',
            hour=hour,
            minute=minute,
            timezone='Europe/Moscow'
        )
        print(f"⏰ Запланирован ежедневный парсинг на {hour:02d}:{minute:02d}")
    except Exception as e:
        print(f"❌ Ошибка настройки расписания: {str(e)}")

def run_scheduled_parse():
    """Запуск парсинга по расписанию"""
    global parsing_in_progress
    
    if parsing_in_progress:
        print("⏳ Пропуск автоматического парсинга: уже выполняется другой парсинг")
        return
    
    admin_id = os.getenv("TELEGRAM_ADMIN_ID")
    if not admin_id:
        print("❌ ADMIN_ID не задан, автоматический парсинг не запущен")
        return
    
    print(f"⏰ Запуск автоматического парсинга по расписанию")
    parsing_in_progress = True
    
    # Сбрасываем состояние логов
    global current_log_message
    current_log_message = None
    while not log_queue.empty():
        log_queue.get()
    
    # Запускаем парсинг в отдельном потоке
    threading.Thread(
        target=run_parser, 
        args=(config.DEFAULT_TYPE,),
        kwargs={'is_scheduled': True},
        daemon=True
    ).start()

async def log_updater(chat_id: int):
    """Периодически обновляет сообщение с логами"""
    global parsing_in_progress
    
    while parsing_in_progress or not log_queue.empty():
        await update_log_message(chat_id)
        await asyncio.sleep(2)
    
    # Финальное обновление
    await update_log_message(chat_id)
    
    # Отправляем результат только если парсинг завершен
    if not parsing_in_progress:
        await send_parse_results(chat_id)

async def send_parse_results(chat_id: int):
    """Отправляет результаты парсинга администратору"""
    try:
        # Ищем последний созданный файл с номерами
        output_dir = "output"
        phone_files = [f for f in os.listdir(output_dir) if f.startswith("phones_") and f.endswith(".txt")]
        
        if phone_files:
            # Сортируем по времени создания и берем самый новый
            latest_file = max(phone_files, key=lambda f: os.path.getctime(os.path.join(output_dir, f)))
            file_path = os.path.join(output_dir, latest_file)
            
            file = FSInputFile(file_path)
            await bot.send_document(
                chat_id=chat_id,
                document=file,
                caption="📄 Результат автоматического парсинга"
            )
            
            # Запускаем автоудаление файла через 10 секунд
            asyncio.create_task(delete_file_after_delay(file_path, delay_seconds=10))
        else:
            await bot.send_message(
                chat_id, 
                "❌ Файл с результатами не найден.\n\n"
                "Возможно, не было найдено номеров для выбранного типа авторов."
            )
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Не удалось отправить результаты: {str(e)}")

async def main():
    """Основная функция запуска бота"""
    global bot_task
    
    # Настраиваем автоматический парсинг при запуске
    schedule_daily_parse()
    scheduler.start()
    
    # Запускаем бота в фоновой задаче
    bot_task = asyncio.create_task(dp.start_polling(bot))
    
    # Бесконечный цикл для проверки состояния парсинга
    while True:
        try:
            # Если идет автоматический парсинг, обновляем логи
            if parsing_in_progress:
                admin_id = os.getenv("TELEGRAM_ADMIN_ID")
                if admin_id:
                    await log_updater(int(admin_id))
            
            # Проверяем каждые 10 секунд
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Ошибка в основном цикле: {str(e)}")
            # Перезапускаем задачу бота при необходимости
            if bot_task.done():
                bot_task = asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())