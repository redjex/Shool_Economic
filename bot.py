import telebot
from telebot import types
import json
import os
import io
import segno
import threading
import time
import math
from PIL import Image, ImageDraw, ImageFont

# Глобальное состояние для навигации по магазину
current_index_state = {}

# ----------------------- Константы -----------------------
TOKEN = ''
# Старый пакет для покупки опыта (использовался ранее)
EXP_COST = 5      # стоимость покупки опыта (SC Coin) для 10 опыта
EXP_GAIN = 10     # сколько опыта даётся за покупку (старый вариант)

# Пути к файлам
DATA_FILE = r'data\fio.json'
REKLAMA_FILE = r'data\reklama.json'
QR_CODES_FILE = r'data\qr_codes.json'

# Глобальный список товаров (добавить после импортов)
ITEMS = [
    {"image": "3.jpg", "price": 30, "grade": 3},  # Индекс 1 (1-based)
    {"image": "2.jpg", "price": 40, "grade": 4},  # Индекс 2
    {"image": "1.jpg", "price": 50, "grade": 5}   # Индекс 3
]



def delete_message_after_delay(chat_id, message_id, delay):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        print(f"Ошибка удаления сообщения: {e}")

# ----------------------- Инициализация бота -----------------------

bot = telebot.TeleBot(TOKEN)

# ----------------------- Вспомогательные функции -----------------------
def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Обеспечиваем наличие необходимых ключей у каждого пользователя
    for user_id, user_info in data.items():
        user_info.setdefault('exp', 0)
        user_info.setdefault('level', 1)
        user_info.setdefault('sc_coin', 0)
        user_info.setdefault('cart', [])
    return data

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка при сохранении данных: {e}")

def load_reklama():
    with open(REKLAMA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_reklama(text, photo):
    with open(REKLAMA_FILE, 'w', encoding='utf-8') as f:
        json.dump({"text": text, "photo": photo}, f, ensure_ascii=False, indent=4)

def load_qr_codes():
    with open(QR_CODES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_qr_codes(qr_codes):
    with open(QR_CODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(qr_codes, f, ensure_ascii=False, indent=4)

def generate_unique_user_id(user_data):
    user_ids = set(user_data.keys())
    new_user_id = 1
    while str(new_user_id) in user_ids:
        new_user_id += 1
    return str(new_user_id)

def get_threshold(level):
    """
    Возвращает суммарное количество опыта, необходимое для достижения уровня `level`.
    Для уровня 1 порог равен 0, для 2 – 10, для 3 – 10+20=30, для 4 – 10+20+30=60 и т.д.
    """
    return sum(i * 10 for i in range(1, level))

def create_level_image(user_info):
    """
    Создаёт изображение с информацией о прогрессе уровня.
    Используется текущий уровень, суммарный опыт и расчёт прогресса до следующего уровня.
    """
    current_level = user_info.get('level', 1)
    total_exp = user_info.get('exp', 0)
    base_image = Image.open(r'image\level_base.jpg')
    
    # Если изображение в RGBA, конвертируем в RGB
    if base_image.mode == 'RGBA':
        base_image = base_image.convert('RGB')
    
    draw = ImageDraw.Draw(base_image)
    
    try:
        level_font = ImageFont.truetype("arial.ttf", 100)
        exp_font = ImageFont.truetype("arial.ttf", 40)
    except:
        level_font = ImageFont.load_default()
        exp_font = ImageFont.load_default()
    
    current_threshold = get_threshold(current_level)
    next_threshold = get_threshold(current_level + 1)
    current_progress = total_exp - current_threshold
    required_for_next = next_threshold - current_threshold  # например, current_level * 10

    level_text = f"{current_level}"
    text_width = draw.textlength(level_text, font=level_font)
    draw.text(((base_image.width - text_width) // 2, 100), level_text, font=level_font, fill="white")
    
    progress_width = 800
    progress_height = 40
    progress_x = (base_image.width - progress_width) // 2
    progress_y = 400

    draw.rectangle([(progress_x, progress_y), (progress_x + progress_width, progress_y + progress_height)], fill="#444444")
    fill_width = int((current_progress / required_for_next) * progress_width) if required_for_next > 0 else progress_width
    draw.rectangle([(progress_x, progress_y), (progress_x + fill_width, progress_y + progress_height)], fill="#4CAF50")
    
    progress_text = f"{current_progress}/{required_for_next}"
    text_width = draw.textlength(progress_text, font=exp_font)
    draw.text(((base_image.width - text_width) // 2, progress_y + progress_height + 10), progress_text, font=exp_font, fill="white")
    
    buf = io.BytesIO()
    base_image.save(buf, format='JPEG')
    buf.seek(0)
    return buf

# ----------------------- Команды и обработчики -----------------------

def show_main_menu(chat_id, message_id=None):
    user_data = load_data()
    user_info = next((info for info in user_data.values() if info.get('telegram_id') == chat_id), None)
    if not user_info:
        bot.send_message(chat_id, "Профиль не найден.")
        return

    markup = types.InlineKeyboardMarkup()
    # Кнопки меню
    shop_button = types.InlineKeyboardButton("Магазин", callback_data='shop_menu')
    profile_button = types.InlineKeyboardButton("Профиль", callback_data='profile')
    if user_info.get('cart'):
        cart_button = types.InlineKeyboardButton("Корзина", callback_data='cart')
        markup.add(shop_button, cart_button, profile_button)
    else:
        markup.add(shop_button, profile_button)

    bot.send_chat_action(chat_id, 'typing')
    with open(r'image\main.jpg', 'rb') as photo:
        if message_id:
            try:
                bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=types.InputMediaPhoto(photo),
                    reply_markup=markup
                )
                bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption="Добро пожаловать в главное меню!",
                    reply_markup=markup
                )
            except Exception as e:
                print(f"Ошибка при редактировании сообщения: {e}")
                bot.send_photo(chat_id, photo, caption="Добро пожаловать в главное меню!", reply_markup=markup)
        else:
            bot.send_photo(chat_id, photo, caption="Добро пожаловать в главное меню!", reply_markup=markup)

@bot.message_handler(commands=['menu'])
def handle_menu_command(message):
    chat_id = message.chat.id
    show_main_menu(chat_id)

@bot.message_handler(commands=['help'])
def handle_help_command(message):
    help_text = (
        "📞 Мои контакты:\n\n"
        "🔹 Telegram: [@redjexs](https://t.me/redjexs)\n"
        "🔹 VK: [redjex](https://vk.com/redjex)\n\n"
        "По всем вопросам обращайтесь в личные сообщения!"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if message.text.startswith('/start activate_'):
        qr_code_id = message.text.split('activate_')[1]
        activate_qr_code(chat_id, qr_code_id)
    else:
        user_data = load_data()
        user_info = next((info for info in user_data.values() if info.get('telegram_id') == chat_id), None)
        if not user_info:
            keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            button_phone = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
            keyboard.add(button_phone)
            msg = bot.send_message(chat_id, "Отправьте свой номер телефона:", reply_markup=keyboard)
            bot.register_next_step_handler(msg, show_profile)
        else:
            show_main_menu(chat_id)

def show_profile(message_or_chat_id):
    if hasattr(message_or_chat_id, 'chat'):
        chat_id = message_or_chat_id.chat.id
        phone = message_or_chat_id.contact.phone_number if message_or_chat_id.contact else None
    else:
        chat_id = message_or_chat_id
        phone = None

    user_data = load_data()
    user_info = next((info for info in user_data.values() if info.get('telegram_id') == chat_id), None)
    if not user_info:
        new_user_id = generate_unique_user_id(user_data)
        user_info = {
            "telegram_id": chat_id,
            "phone": phone,
            "exp": 0,
            "level": 1,
            "sc_coin": 0,
            "cart": [],
            "user_number": int(new_user_id)
        }
        user_data[new_user_id] = user_info
        save_data(user_data)

    next_threshold = get_threshold(user_info['level'] + 1)
    exp_needed = next_threshold - user_info.get('exp', 0)
    if exp_needed < 0:
        exp_needed = 0

    profile_text = (
        f"📞  Номер телефона: {user_info.get('phone', 'не указан')}\n"
        f"💵  SC Coin: {user_info.get('sc_coin', 0)}\n"
        f"💎  Опыт: {user_info.get('exp', 0)}\n"
        f"🔼  Уровень: {user_info.get('level', 1)}\n"
        f"🔢  Порядковый номер: {user_info.get('user_number')}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Показать прогресс уровня", callback_data='show_progress'))
    markup.add(types.InlineKeyboardButton("Назад", callback_data='back_to_menu'))

    with open(r'image\profile.jpg', 'rb') as photo:
        bot.send_photo(chat_id, photo, caption=profile_text, reply_markup=markup)

# --------------- НОВОЕ МЕНЮ МАГАЗИНА ---------------

@bot.callback_query_handler(func=lambda call: call.data == 'shop_menu')
def shop_menu_handler(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup()
    grade_button = types.InlineKeyboardButton("Купить оценку", callback_data="shop_grade")
    exp_button = types.InlineKeyboardButton("Купить опыт", callback_data="shop_exp")
    back_button = types.InlineKeyboardButton("Назад", callback_data="back_to_menu")
    markup.add(grade_button, exp_button)
    markup.add(back_button)
    with open(r'image\market.jpg', 'rb') as photo:
        bot.send_photo(chat_id, photo, caption="Магазин", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'shop_grade')
def shop_grade_handler(call):
    chat_id = call.message.chat.id
    max_index = len(ITEMS)
    if max_index == 0:
        bot.send_message(chat_id, "❌ Магазин пуст!")
        return
    show_shop(chat_id, max_index, call.message.message_id)



@bot.callback_query_handler(func=lambda call: call.data == 'shop_exp')
def shop_exp_handler(call):
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup()
    button10 = types.InlineKeyboardButton("10", callback_data="buy_exp_10")
    button20 = types.InlineKeyboardButton("20", callback_data="buy_exp_20")
    button50 = types.InlineKeyboardButton("50", callback_data="buy_exp_50")
    buttonCustom = types.InlineKeyboardButton("Своё кол-во", callback_data="buy_exp_custom")
    back_button = types.InlineKeyboardButton("Назад", callback_data="back_to_shop")
    markup.row(button10, button20, button50)
    markup.row(buttonCustom)
    markup.row(back_button)
    with open(r'image\exp.jpg', 'rb') as photo:
        bot.send_photo(chat_id, photo, caption="Покупка опыта", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_shop')
def back_to_shop_handler(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    shop_menu_handler(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_exp_"))
def buy_exp_options_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    if data == "buy_exp_10":
        amount = 10
        cost = 5
        buy_experience(chat_id, amount, cost)
        bot.answer_callback_query(call.id)
    elif data == "buy_exp_20":
        amount = 20
        cost = 9
        buy_experience(chat_id, amount, cost)
        bot.answer_callback_query(call.id)
    elif data == "buy_exp_50":
        amount = 50
        cost = 20
        buy_experience(chat_id, amount, cost)
        bot.answer_callback_query(call.id)
    elif data == "buy_exp_custom":
        bot.send_message(chat_id, "Введите желаемое количество опыта:")
        bot.register_next_step_handler(call.message, process_custom_exp)

def process_custom_exp(message):
    chat_id = message.chat.id
    try:
        amount = int(message.text)
        if amount <= 0:
            bot.send_message(chat_id, "Введите положительное число опыта.")
            return
    except ValueError:
        bot.send_message(chat_id, "Пожалуйста, введите число.")
        return
    cost = math.ceil(amount * 0.5)
    buy_experience(chat_id, amount, cost)

def buy_experience(chat_id, amount, cost):
    user_data = load_data()
    user_info = next((u for u in user_data.values() if u.get('telegram_id') == chat_id), None)
    if not user_info:
        bot.send_message(chat_id, "Профиль не найден!")
        return
    if user_info.get('sc_coin', 0) < cost:
        bot.send_message(chat_id, f"❌ Недостаточно SC Coin! Для покупки {amount} опыта требуется {cost} SC Coin.")
        return
    user_info['sc_coin'] -= cost
    user_info['exp'] += amount
    while user_info['exp'] >= get_threshold(user_info['level'] + 1):
        user_info['level'] += 1
        bot.send_message(chat_id, f"🎉 Поздравляем! Вы достигли {user_info['level']} уровня!")
    save_data(user_data)
    bot.send_message(chat_id, f"✅ Вы купили {amount} опыта за {cost} SC Coin!")

@bot.callback_query_handler(func=lambda call: call.data == 'buy_exp')
def buy_exp(call):
    shop_exp_handler(call)

@bot.callback_query_handler(func=lambda call: call.data == 'show_progress')
def show_progress(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    chat_id = call.message.chat.id
    user_data = load_data()
    user_info = next((u for u in user_data.values() if u.get('telegram_id') == chat_id), None)
    if not user_info:
        bot.answer_callback_query(call.id, "Профиль не найден!")
        return
    level_image = create_level_image(user_info)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Назад", callback_data='profile'))
    bot.send_photo(chat_id, level_image, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'delete_qr')
def handle_delete_qr(call):
    chat_id = call.message.chat.id
    bot.delete_message(chat_id, call.message.message_id)
    bot.answer_callback_query(call.id, "✅ QR‑код успешно удалён")

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def callback_profile(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_profile(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == 'delete_cart_message')
def delete_cart_message(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "🗑️ Корзина закрыта")
    except Exception as e:
        print(f"Ошибка удаления сообщения: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(f"Ошибка удаления сообщения: {e}")
    show_main_menu(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def shop_handler(call):
    chat_id = call.message.chat.id
    index = int(call.data.split("_")[1])
    current_index_state[chat_id] = int(index)
    show_shop(chat_id, int(index), call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "cart")
def show_cart_handler(call):
    show_cart(call.message.chat.id)

# Обработчик для покупки рейтинговых товаров (оценок)
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_item_"))
def buy_rating_handler(call):
    try:
        item_index = int(call.data.split("_")[2])  # Получаем индекс товара
        buy_shop_item(call, item_index)
    except Exception as e:
        print(f"Ошибка покупки: {e}")
        bot.answer_callback_query(call.id, "Ошибка при покупке")

def buy_shop_item(call, item_index):
    chat_id = call.message.chat.id
    user_data = load_data()
    user_info = next((u for u in user_data.values() if u['telegram_id'] == chat_id), None)
    
    if not user_info:
        bot.answer_callback_query(call.id, "Профиль не найден!")
        return
    
    # Проверяем корректность индекса
    if 1 <= item_index <= len(ITEMS):
        item = ITEMS[item_index - 1]  # Конвертируем в 0-based индекс
    else:
        bot.answer_callback_query(call.id, "Неверный товар")
        return
    
    if user_info['sc_coin'] >= item['price']:
        user_info['sc_coin'] -= item['price']
        user_info['cart'].append(item_index)  # Сохраняем 1-based индекс
        save_data(user_data)
        bot.answer_callback_query(
            call.id,
            text=f"✅ Вы купили оценку {item['grade']}!", 
            show_alert=True
        )
    else:
        bot.answer_callback_query(call.id, "❌ Недостаточно SC Coin!")

def buy_rating_item(call, rating):
    chat_id = call.message.chat.id
    user_data = load_data()
    user_info = next((u for u in user_data.values() if u.get('telegram_id') == chat_id), None)
    if not user_info:
        bot.answer_callback_query(call.id, "Профиль не найден!")
        return
    
    # Правильное сопоставление оценки с индексом товара
    grade_to_index = {3: 0, 4: 1, 5: 2}  # 3 -> ITEMS[0], 4 -> ITEMS[1], 5 -> ITEMS[2]
    
    if rating not in grade_to_index:
        bot.answer_callback_query(call.id, "Неверный товар")
        return
    
    item_index = grade_to_index[rating]
    item = ITEMS[item_index]
    
    if user_info.get('sc_coin', 0) >= item['price']:
        user_info['sc_coin'] -= item['price']
        # Сохраняем индекс товара вместо изображения
        user_info['cart'].append(item_index + 1)  # +1 для 1-based номера
        save_data(user_data)
        bot.answer_callback_query(
            call.id,
            text=f"✅ Вы купили оценку {item['grade']}!",
            show_alert=True
        )
    else:
        bot.answer_callback_query(call.id, "❌ Недостаточно SC Coin!")


def show_cart(chat_id):
    user_data = load_data()
    user_info = next((info for info in user_data.values() if info['telegram_id'] == chat_id), None)
    if not user_info or not user_info.get('cart'):
        bot.send_message(chat_id, "🛒 Ваша корзина пуста")
        return

    cart_items = user_info['cart']
    cart_text = "📦 Ваша корзина:\n\n"
    for item_index in cart_items:
        if isinstance(item_index, int) and 1 <= item_index <= len(ITEMS):
            item = ITEMS[item_index - 1]  # Конвертируем 1-based в 0-based индекс
            cart_text += f"• Оценка {item['grade']} (Цена: {item['price']} SC Coin)\n"
        else:
            print(f"Ошибка: Неверный индекс товара в корзине ({item_index})")
            continue

    markup = types.InlineKeyboardMarkup()
    for item_index in cart_items:
        if isinstance(item_index, int) and 1 <= item_index <= len(ITEMS):
            item = ITEMS[item_index - 1]
            markup.add(types.InlineKeyboardButton(
                f"Получить QR для оценки {item['grade']}",
                callback_data=f"create_qr_{user_info['user_number']}_{item_index}"
            ))
    
    back_button = types.InlineKeyboardButton("Назад", callback_data='delete_cart_message')
    markup.add(back_button)
    
    with open(r'image\cart.jpg', 'rb') as photo:
        bot.send_photo(chat_id, photo, caption=cart_text, reply_markup=markup)


def show_shop(chat_id, index, message_id=None):
    if not (1 <= index <= len(ITEMS)):
        bot.send_message(chat_id, "❌ Неверный индекс товара!")
        return
    item = ITEMS[index - 1]
    caption = f"Цена: {item['price']} SC Coin"
    markup = types.InlineKeyboardMarkup()
    # Кнопки навигации: задаём фиксированные callback_data "<" и ">"
    prev_button = types.InlineKeyboardButton("<", callback_data="<")
    next_button = types.InlineKeyboardButton(">", callback_data=">")
    # Кнопка-счётчик просто отображает текущую позицию, без обработки нажатия
    counter_button = types.InlineKeyboardButton(f"{len(ITEMS) - index + 1}/{len(ITEMS)}", callback_data="counter")
    buy_button = types.InlineKeyboardButton("Купить", callback_data=f"buy_item_{index}")
    back_button = types.InlineKeyboardButton("Назад", callback_data='back_to_menu')
    
    markup.add(prev_button, counter_button, next_button)
    markup.add(buy_button)
    markup.add(back_button)
    
    bot.send_chat_action(chat_id, 'typing')
    with open(f'image\\shop\\{item["image"]}', 'rb') as photo:
        if message_id:
            try:
                bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=types.InputMediaPhoto(photo),
                    reply_markup=markup
                )
                bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=caption,
                    reply_markup=markup
                )
            except Exception as e:
                print(f"Ошибка при редактировании сообщения: {e}")
        else:
            bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    if call.data == "profile":
        bot.delete_message(chat_id, call.message.message_id)
        show_profile(chat_id)
    elif call.data == 'delete_cart_message':
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "🗑️ Корзина закрыта")
        except Exception as e:
            print(f"Ошибка удаления сообщения: {e}")
    elif call.data == "back_to_menu":
        bot.delete_message(chat_id, call.message.message_id)
        show_main_menu(chat_id)
    # Если нажата кнопка с callback "shop_*" (например, при выборе конкретного товара) 
    elif call.data.startswith("shop_"):
        index = call.data.split("_")[1]
        current_index_state[chat_id] = int(index)
        show_shop(chat_id, int(index), call.message.message_id)
    # Обработка цикличной навигации
    elif call.data == "<":
        current_index = current_index_state.get(chat_id, 1)
        current_index = 3 if current_index == 1 else current_index - 1
        current_index_state[chat_id] = current_index
        show_shop(chat_id, current_index, call.message.message_id)
    elif call.data == ">":
        current_index = current_index_state.get(chat_id, 1)
        current_index = 1 if current_index == 3 else current_index + 1
        current_index_state[chat_id] = current_index
        show_shop(chat_id, current_index, call.message.message_id)
    elif call.data == "cart":
        show_cart(chat_id)
    elif call.data.startswith("buy_"):
        try:
            index = int(call.data.split("_")[1])
            buy_shop_item(call, index)
        except Exception as e:
            print(f"Ошибка покупки: {e}")
            bot.answer_callback_query(call.id, "Ошибка при покупке")
    elif call.data.startswith("create_qr_"):
        parts = call.data.split("_")
        if len(parts) == 4:
            user_id = parts[2]
            item_number = parts[3]
            create_qr_code(chat_id, user_id, item_number)

        
# Функция для генерации QR-кода
def create_qr_code(chat_id, user_number, item_number):
    try:
        # Преобразуем входные параметры в целые числа
        user_number = int(user_number)
        item_number = int(item_number)
    except ValueError:
        bot.send_message(chat_id, "❌ Ошибка в данных запроса")
        return

    # Загружаем данные пользователей и QR‑кодов
    user_data = load_data()
    qr_codes = load_qr_codes()

    # Находим информацию о пользователе
    user_info = next(
        (u for u in user_data.values() if u['user_number'] == user_number and u['telegram_id'] == chat_id),
        None
    )
    if not user_info:
        bot.send_message(chat_id, "❌ Пользователь не найден")
        return

    # Проверяем, есть ли указанный товар в корзине пользователя
    if item_number not in user_info.get('cart', []):
        bot.send_message(chat_id, "❌ Товар отсутствует в корзине")
        return

    # Генерируем уникальный ключ для QR‑кода (этот ключ можно сохранить для дальнейшей активации, если требуется)
    qr_code_key = f"{user_number}_{item_number}_{int(time.time())}"

    # Создаём QR‑код с нужной ссылкой
    try:
        qr = segno.make(f"https://t.me/School_economics_bot?start=activate_{qr_code_key}")
    except Exception as e:
        bot.send_message(chat_id, "❌ Ошибка при генерации QR‑кода")
        return

    # Сохраняем QR‑код в буфер
    img_buffer = io.BytesIO()
    try:
        qr.save(img_buffer, kind="png", scale=10)
    except Exception as e:
        bot.send_message(chat_id, "❌ Ошибка при сохранении изображения QR‑кода")
        return
    img_buffer.seek(0)

    # (Необязательно) Сохраняем информацию о QR‑коде
    qr_codes[qr_code_key] = {
        "user_id": chat_id,
        "user_number": user_number,
        "item_number": item_number,
        "activated": False,
        "timestamp": time.time()
    }
    save_qr_codes(qr_codes)
    # Создаем клавиатуру с кнопкой "Удалить"
    markup = types.InlineKeyboardMarkup()
    delete_button = types.InlineKeyboardButton("🗑️ Удалить", callback_data="delete_qr")
    markup.add(delete_button)

    # Отправляем фото и инлайн клавиатуру в одном сообщении
    bot.send_photo(
        chat_id,
        img_buffer,
        caption=f"🔐 QR‑код для оценки {ITEMS[item_number-1]['grade']}\n⏳ Срок действия: 24 часа",
        reply_markup=markup
    )

    

def activate_qr_code(chat_id, qr_code_id):
    qr_codes = load_qr_codes()
    
    if qr_code_id not in qr_codes:
        bot.send_message(chat_id, "❌ Код не найден или устарел")
        return

    qr_data = qr_codes[qr_code_id]
    
    # Проверка срока действия (24 часа)
    if time.time() - qr_data['timestamp'] > 86400:
        bot.send_message(chat_id, "⌛ Срок действия кода истёк")
        del qr_codes[qr_code_id]
        save_qr_codes(qr_codes)
        return

    if qr_data['activated']:
        bot.send_message(chat_id, "⚠️ Код уже использован")
        return

    # Обновляем данные
    user_data = load_data()
    user_info = next(
        (u for u in user_data.values() 
         if u['user_number'] == qr_data['user_number']),
        None
    )

    if user_info and qr_data['item_number'] in user_info.get('cart', []):
        # Удаляем из корзины
        user_info['cart'].remove(qr_data['item_number'])
        qr_data['activated'] = True
        
        # Добавляем оценку в профиль
        if 'grades' not in user_info:
            user_info['grades'] = []
        user_info['grades'].append(ITEMS[qr_data['item_number']-1]['grade'])
        
        # Сохраняем изменения
        save_data(user_data)
        save_qr_codes(qr_codes)
        
        # Отправляем уведомления
        msg = bot.send_message(
            chat_id,
            f"✅ Оценка {ITEMS[qr_data['item_number']-1]['grade']} активирована!"  # Исправлено
        )
        bot.send_message(
            qr_data['user_id'],
            f"🎉 Ваша оценка {ITEMS[qr_data['item_number']-1]['grade']} активирована!"
        )



# ----------------------- Команда для учителей -----------------------
TEACHER_IDS = []
@bot.message_handler(commands=['add_points'])
def add_points(message):
    if message.from_user.id not in TEACHER_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return
    args = message.text.split()[1:]
    if len(args) != 2:
        bot.send_message(message.chat.id, "Неправильный формат команды. Используйте /add_points Порядковый_номер и_кол-во_поинтов.")
        return
    user_number, points = args
    try:
        user_number = int(user_number)
        points = int(points)
    except ValueError:
        bot.send_message(message.chat.id, "Неверные данные. Убедитесь, что вы ввели числовые значения.")
        return
    user_data = load_data()
    user_info = next((info for info in user_data.values() if info.get('user_number') == user_number), None)
    if not user_info:
        bot.send_message(message.chat.id, "Пользователь не найден.")
        return
    user_info['sc_coin'] = user_info.get('sc_coin', 0) + points
    save_data(user_data)
    bot.send_message(message.chat.id, f"Добавлено {points} SC Coin пользователю с порядковым номером {user_number}.")

# ----------------------- Запуск бота -----------------------
bot.polling(none_stop=True)
