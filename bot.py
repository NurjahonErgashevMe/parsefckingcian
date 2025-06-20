import os
import json
import time
import asyncio
import queue
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

# Загрузка переменных окружения
load_dotenv()

# Импорт модулей парсера
import utils
import parser_ads
import phones_parser
import config

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

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    markup = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="🚀 Парсить")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 Привет! Я бот для парсинга телефонных номеров с CIAN.\n\n"
        "🎯 Бот умеет парсить номера от разных типов авторов:\n"
        "• 🏗️ Застройщики\n"
        "• 🏢 Агенства недвижимостей\n"
        "• 🏠 Владельцы домов\n"
        "• 👔 Риэлторы\n\n"
        "Нажми кнопку '🚀 Парсить' или отправь команду /parse, чтобы начать сбор данных.",
        reply_markup=markup
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
            
            # Спрашиваем о дальнейшем парсинге
            keyboard = create_author_type_keyboard()
            await bot.send_message(
                chat_id=chat_id,
                text="🎯 Какие типы авторов еще нужно спарсить?\n\n"
                     "Выберите тип из списка ниже или нажмите 'Парсинг завершен', если больше ничего не нужно:",
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