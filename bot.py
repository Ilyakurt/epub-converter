import os
import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from converter import convert_file, convert_archive

log_directory = os.path.join(os.getcwd(), 'logs')
config_directory = os.path.join(os.getcwd(), 'config')
os.makedirs(log_directory, exist_ok=True)
os.makedirs(config_directory, exist_ok=True)

logging.basicConfig(filename=os.path.join(log_directory, 'bot_logs.log'), level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Starting bot")

config_file_path = os.path.join(config_directory, 'config.json')
config = {}

if os.path.exists(config_file_path):
    with open(config_file_path) as config_file:
        config = json.load(config_file)

if 'telegram_token' not in config:
    config['telegram_token'] = input("Telegram token not found. Please enter your Telegram bot token: ").strip()
    with open(config_file_path, 'w') as config_file:
        json.dump(config, config_file, indent=4)

TOKEN = config['telegram_token']
router = Router()

# Initialize empty dictionaries for localizations and user settings
localizations = {}
user_settings = {}

def load_localizations():
    """Load localizations from files into a dictionary."""
    for filename in os.listdir('localization'):
        if filename.endswith('.json'):
            lang_code = filename.split('.')[0]
            with open(f'localization/{filename}', encoding='utf-8') as f:
                localizations[lang_code] = json.load(f)

def load_user_settings():
    """Load user settings from a JSON file, or return an empty dict if the file doesn't exist."""
    try:
        with open('user_settings.json') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_settings():
    """Save the current user settings to a JSON file."""
    with open('user_settings.json', 'w') as f:
        json.dump(user_settings, f, indent=4)

def get_localization(chat_id, key):
    """Retrieve a localized string based on the user's language preference."""
    lang_code = user_settings.get(str(chat_id), 'en')
    return localizations[lang_code].get(key, '')

async def download_file(message, document):
    """
    Download the document sent by the user to a local directory.
    """
    download_folder = 'downloads'
    os.makedirs(download_folder, exist_ok=True)  # Ensure the download directory exists
    file = await message.bot.get_file(document.file_id)
    file_path = os.path.join(download_folder, document.file_name)
    await message.bot.download_file(file.file_path, destination=file_path)
    logging.info(f"File {document.file_name} downloaded by user {message.chat.id}")
    return file_path

def process_file(file_path, file_name):
    """
    Process the downloaded file by converting it based on its extension.
    """
    if file_name.endswith('.zip'):
        return convert_archive(file_path)
    else:
        return [convert_file(file_path)]

async def send_converted_files(message, output_files, chat_id):
    """
    Send the converted files back to the user and clean up by removing the files after sending.
    """
    for output_file_path in output_files:
        await message.answer_document(document=FSInputFile(output_file_path))
        logging.info(f"EPUB file {output_file_path} sent to user {chat_id}")
        os.remove(output_file_path)  # Remove the file after sending it

def update_user_statistic(chat_id, update_field, file_count=1):
    """Update statistics for a given user directly in the JSON file."""
    stats_file_path = 'user_statistics.json'
    chat_id_str = str(chat_id)

    try:
        with open(stats_file_path, 'r') as f:
            statistics = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        statistics = {}

    if chat_id_str not in statistics:
        statistics[chat_id_str] = {'files_sent': 0, 'language_changes': 0}

    statistics[chat_id_str][update_field] += file_count

    with open(stats_file_path, 'w') as f:
        json.dump(statistics, f, indent=4)

# Load localizations and user settings at startup
load_localizations()
user_settings = load_user_settings()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Respond to the /start command with a greeting and help information."""
    chat_id = message.chat.id
    if str(chat_id) not in user_settings:
        user_settings[str(chat_id)] = 'en'
        save_user_settings()
    greeting = get_localization(chat_id, 'greeting')
    help_command_info = get_localization(chat_id, 'help_command_info')
    await message.answer(text=f"{greeting}\n{help_command_info}")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Respond to the /help command with information on how to use the bot."""
    chat_id = message.chat.id
    help_text = get_localization(chat_id, 'help_text')
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="English", callback_data="lang_en"),
         types.InlineKeyboardButton(text="Русский", callback_data="lang_ru")]
    ])
    await message.answer(text=help_text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("lang_"))
async def button_handler(callback_query: types.CallbackQuery):
    """Handle language selection buttons."""
    chat_id = callback_query.from_user.id
    new_lang_code = callback_query.data[5:]
    user_settings[str(chat_id)] = new_lang_code
    save_user_settings()
    await callback_query.message.delete()
    await cmd_help(callback_query.message)
    update_user_statistic(chat_id, 'language_changes')

@router.message(F.content_type == types.ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    """Process document messages, converting supported file types and updating user statistics."""
    chat_id = message.chat.id
    document = message.document
    file_supported = document.file_name.endswith(('.zip', '.fb2'))

    if not file_supported:
        error_file_format = get_localization(chat_id, 'error_file_format')
        await message.answer(text=error_file_format)
        return

    try:
        file_path = await download_file(message, document)
        output_files = process_file(file_path, document.file_name)

        file_count = len(output_files) if document.file_name.endswith('.zip') else 1

        await send_converted_files(message, output_files, chat_id)
        update_user_statistic(chat_id, 'files_sent', file_count)  # Pass file_count
    except Exception as e:
        logging.error(f"Error processing file {document.file_name} for user {chat_id}: {str(e)}")
        error_conversion = get_localization(chat_id, 'error_conversion')
        await message.answer(text=error_conversion)

async def main():
    """Initialize the bot and start polling for updates."""
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())