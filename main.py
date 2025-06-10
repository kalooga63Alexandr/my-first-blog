import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv


load_dotenv()

# Константы для путей
IMAGE_DIR = os.getenv('SAVE_DIRECTORY', 'images')
os.makedirs(IMAGE_DIR, exist_ok=True)


# Доступные цвета текста
COLORS = {
    'red': '#FF0000',
    'blue': '#0000FF',
    'green': '#00FF00',
    'yellow': '#FFFF00',
    'white': '#FFFFFF',
    'black': '#000000'
}


# Очистка старых файлов при старте
def cleanup_old_files():
    now = datetime.now()
    for filename in os.listdir(IMAGE_DIR):
        file_path = os.path.join(IMAGE_DIR, filename)
        if os.path.isfile(file_path):
            # Удаляем файлы старше 1 часа
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (now - file_time).total_seconds() > 3600:
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

# Удаление временных файлов


def delete_temp_files(*filenames):
    for filename in filenames:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as e:
                print(f"Error deleting file {filename}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне изображение после отправь текст и выбери для него цвет\n"
                                    "я добавлю текст на изображение.\nТы сможешь переслать его \nили отправить в группу")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Я бот, который добавляет текст на изображения!\n"
        "1. Отправьте мне изображение\n"
        "2. Введите текст для добавления\n"
        "3. Получите результат с текстом по центру\n"
        "Команды:\n"
        "/start - начать общение\n"
        "/help - справка"
    )
    await update.message.reply_text(help_text)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    file = await update.message.photo[-1].get_file()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    original_filename = os.path.join(
        IMAGE_DIR, f"{timestamp}_{user_id}_original.jpg")
    edited_filename = os.path.join(
        IMAGE_DIR, f"{timestamp}_{user_id}_edited.jpg")

    await file.download_to_drive(original_filename)
    context.user_data['image_paths'] = {
        'original': original_filename,
        'edited': edited_filename
    }
    await update.message.reply_text("Теперь введите текст для добавления на изображение:")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'image_paths' not in context.user_data:
        await update.message.reply_text("Пожалуйста, сначала отправьте изображение.")
        return

    user_text = update.message.text
    context.user_data['text_to_add'] = user_text

    # Создаем кнопки для выбора цвета текста
    color_buttons = [
        [InlineKeyboardButton(color.capitalize(), callback_data=f"text_color_{color}")
         for color in list(COLORS.keys())[i:i+2]]
        for i in range(0, len(COLORS), 2)
    ]

    await update.message.reply_text(
        "Выберите цвет текста:",
        reply_markup=InlineKeyboardMarkup(color_buttons)
    )


async def handle_text_color_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    # Получаем выбранный цвет
    chosen_color = query.data.split('_')[-1]
    text_color = COLORS[chosen_color]

    # Получаем сохраненные данные
    original_filename = context.user_data['image_paths']['original']
    edited_filename = context.user_data['image_paths']['edited']
    user_text = context.user_data['text_to_add']

    try:
        with Image.open(original_filename) as image:
            draw = ImageDraw.Draw(image)

            # Начальный размер шрифта
            font_size = 150
            font = ImageFont.truetype("fonts/Lobster-Regular.ttf", font_size)

            # Проверяем, помещается ли текст в изображение
            bbox = draw.textbbox((0, 0), user_text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

            # Уменьшаем размер шрифта, пока текст не поместится
            while text_width > image.width - 20 or text_height > image.height - 20:
                font_size -= 1
                font = ImageFont.truetype(
                    "fonts/Lobster-Regular.ttf", font_size)
                bbox = draw.textbbox((0, 0), user_text, font=font)
                text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

            # Центрируем текст
            x = (image.width - text_width) / 2
            y = (image.height - text_height) / 2

            # Рисуем текст с выбранным цветом (фон останется черным по умолчанию)
            draw.text(
                (x, y),
                user_text,
                fill=text_color,
                font=font,
                stroke_width=2,
                stroke_fill="black"  # Фиксированный черный цвет для обводки
            )

            image.save(edited_filename)

            await query.edit_message_text("Ваше изображение готово:")
            await context.bot.send_photo(chat_id=query.message.chat.id, photo=open(edited_filename, 'rb'))

            # Кнопки для отправки в группу
            keyboard = [
                [InlineKeyboardButton(
                    "Отправить в группу", callback_data='send_to_group')],
                [InlineKeyboardButton("Не отправлять", callback_data='cancel')]
            ]
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text="Хотите отправить это изображение в группу?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        await query.edit_message_text(f"Ошибка: {e}")
        delete_temp_files(original_filename, edited_filename)
        context.user_data.pop('image_paths', None)


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if 'image_paths' not in context.user_data:
        await query.edit_message_text("Изображение не найдено.")
        return

    original_filename = context.user_data['image_paths']['original']
    edited_filename = context.user_data['image_paths']['edited']

    if query.data == 'send_to_group':

        try:
            group_id = os.getenv("GROUP_ID")

            with open(edited_filename, 'rb') as photo:
                await context.bot.send_photo(chat_id=group_id, photo=photo)
            await query.edit_message_text("Изображение отправлено в группу!")
        except Exception as e:
            await query.edit_message_text(f"Ошибка отправки: {e}")
    elif query.data == 'cancel':
        await query.edit_message_text("Отправка отменена.")
    else:
        await query.edit_message_text("что-то пошло не так")
    # Всегда удаляем временные файлы после обработки
    delete_temp_files(original_filename, edited_filename)
    context.user_data.pop('image_paths', None)


async def error_handler(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка. Попробуйте еще раз.")


def main():
    cleanup_old_files()  # Очистка при старте

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(
        handle_text_color_choice, pattern="^text_color_"))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == '__main__':
    main()
