import os
import json
import time
import asyncio
import queue
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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

def run_parser(author_type=None):
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
            'rieltor': '👔 риэлторы'
        }
        author_display = author_names.get(author_type, '👥 все типы')
        log_callback(f"🎯 Тип авторов: {author_display}")
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
                        author_type=author_type
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
                author_type=author_type
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
                    author_type=author_type
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
                callback_data=AuthorTypeCallback(type="rieltor").pack()
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
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Изменить регион")],
            [KeyboardButton(text="Список регионов")],
            [KeyboardButton(text="Выбрать комнаты")],
            [KeyboardButton(text="Назад в меню")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"⚙️ <b>Текущие настройки парсинга:</b>\n"
        f"• <b>Регион:</b> {current_region}\n"
        f"• <b>ID региона:</b> {region_id}\n"
        f"• <b>Комнаты:</b> {', '.join(map(str, current_rooms))}\n"
        f"{created_at_info}\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

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
        'rieltor': '👔 риэлторы'
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

async def log_updater(chat_id: int):
    """Периодически обновляет сообщение с логами"""
    global parsing_in_progress
    
    while parsing_in_progress or not log_queue.empty():
        await update_log_message(chat_id)
        await asyncio.sleep(2)  # Пауза между обновлениями
    
    # Финальное обновление
    await update_log_message(chat_id)
    
    # Отправляем результат
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
                caption="📄 Результат парсинга"
            )
            
            # Запускаем автоудаление файла через 10 секунд
            asyncio.create_task(delete_file_after_delay(file_path, delay_seconds=10))
            
            # Спрašиваем о дальнейшем парсинге
            keyboard = create_author_type_keyboard()
            await bot.send_message(
                chat_id=chat_id,
                text="🎯 Какие типы авторов еще нужно спарсить?\n\n"
                     "Выберите тип из списка ниже или нажмите 'Парсинг завершен', если больше ничего не нужно:\n\n"
                     "⚠️ Внимание: файл с результатами будет автоматически удален через 10 секунд для экономии места.",
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id, 
                "❌ Файл с результатами не найден.\n\n"
                "Возможно, не было найдено номеров для выбранного типа авторов."
            )
            
            # Все равно спрашиваем о дальнейшем парсинге
            keyboard = create_author_type_keyboard()
            await bot.send_message(
                chat_id=chat_id,
                text="🎯 Хотите попробовать другой тип авторов?",
                reply_markup=keyboard
            )
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Не удалось отправить файл: {str(e)}")
        
        # В случае ошибки тоже спрашиваем о дальнейшем парсинге
        keyboard = create_author_type_keyboard()
        await bot.send_message(
            chat_id=chat_id,
            text="🎯 Что будем парсить дальше?",
            reply_markup=keyboard
        )

async def main():
    """Основная функция запуска бота"""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())