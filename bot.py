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
from aiogram.types import FSInputFile

# Загрузка переменных окружения
load_dotenv()

# Импорт модулей парсера
import utils
import parser_ads
import phones_parser

# Глобальные переменные для управления состоянием
parsing_in_progress = False
log_queue = queue.Queue()
current_log_message = None

# Инициализация бота
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()

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

def run_parser():
    """Запускает парсер в отдельном потоке"""
    global parsing_in_progress
    
    try:
        utils.ensure_output_dir()
        region_file = utils.get_region_file()
        
        log_callback("\n" + "="*50)
        log_callback(f"CIAN Parser запущен: {datetime.now()}")
        log_callback("="*50)
        
        # Проверяем наличие файла с данными
        if os.path.exists(region_file):
            try:
                with open(region_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if "data" in data and len(data["data"]) > 0:
                    log_callback(f"Найдено {len(data['data'])} объявлений. Начинаем парсинг телефонов...")
                    # Передаем флаг очистки файлов
                    parser = phones_parser.CianPhoneParser(
                        log_callback=log_callback,
                        clear_existing=True
                    )
                    parser.parse()
                    return
                    
            except (json.JSONDecodeError, KeyError) as e:
                log_callback(f"Ошибка чтения файла регионов: {str(e)}. Будет выполнен перепарсинг.")
        
        log_callback("Файл с объявлениями отсутствует или пуст.")
        
        if utils.is_parsing_in_progress():
            log_callback("Парсинг объявлений уже выполняется. Ожидание завершения...")
            
            while utils.is_parsing_in_progress():
                time.sleep(30)
                log_callback("Ожидание...")
            
            log_callback("Парсинг объявлений завершен! Начинаем парсинг телефонов...")
            # Передаем флаг очистки файлов
            parser = phones_parser.CianPhoneParser(
                log_callback=log_callback,
                clear_existing=True
            )
            parser.parse()
        else:
            log_callback("Запускаем парсинг объявлений...")
            if parser_ads.parse_cian_ads(log_callback=log_callback):
                log_callback("Начинаем парсинг телефонов...")
                # Передаем флаг очистки файлов
                parser = phones_parser.CianPhoneParser(
                    log_callback=log_callback,
                    clear_existing=True
                )
                parser.parse()
    
    except Exception as e:
        log_callback(f"❌ Критическая ошибка при парсинге: {str(e)}")
    finally:
        parsing_in_progress = False

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    markup = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Парсить")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 Привет! Я бот для парсинга телефонных номеров с CIAN.\n\n"
        "Нажми кнопку 'Парсить' или отправь команду /parse, чтобы начать сбор данных.",
        reply_markup=markup
    )

@dp.message(Command("parse"))
@dp.message(lambda message: message.text == "Парсить")
async def parse_command(message: types.Message):
    """Обработчик команды /parse"""
    global parsing_in_progress, current_log_message
    
    if parsing_in_progress:
        await message.answer("⚠️ Парсинг уже запущен! Дождитесь завершения.")
        return
    
    # Сбрасываем состояние логов
    current_log_message = None
    while not log_queue.empty():
        log_queue.get()
    
    parsing_in_progress = True
    log_callback("⏳ Подготовка к парсингу...")
    
    # Запускаем парсинг в отдельном потоке
    threading.Thread(target=run_parser, daemon=True).start()
    
    # Запускаем задачу для периодического обновления логов
    asyncio.create_task(log_updater(message.chat.id))

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
        if os.path.exists("output/phones.txt"):
            file = FSInputFile("output/phones.txt")
            await bot.send_document(
                chat_id=chat_id,
                document=file,
                caption="📄 Результат парсинга"
            )
        else:
            await bot.send_message(chat_id, "❌ Файл с результатами не найден")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Не удалось отправить файл: {str(e)}")

async def main():
    """Основная функция запуска бота"""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())