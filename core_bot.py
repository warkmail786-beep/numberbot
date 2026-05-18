import os
import sqlite3
import telebot
from telebot import types
from dotenv import load_dotenv

#=========================================================

#LOAD ENV

#=========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", "0"))

if not BOT_TOKEN: raise Exception("BOT_TOKEN not found in .env")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
DB_PATH = "database.db"
#=========================================================

#DATABASE

#=========================================================

def db_connect():
    return sqlite3.connect(DB_PATH,
check_same_thread=False)

def init_db():
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0.0,
    referred_by INTEGER DEFAULT 0
)
''')

    cursor.execute('''
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
''')

    cursor.execute('''
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    country_name TEXT,
    country_flag TEXT,
    phone_number TEXT UNIQUE,
    rate REAL DEFAULT 0,
    status TEXT DEFAULT 'available',
    assigned_to INTEGER DEFAULT 0
)
''')

    cursor.execute('''
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)
''')

    cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
''')

defaults = [
    ('support_username', 'admin'),
    ('referral_amount', '0.05')
]

for k, v in defaults:
    cursor.execute(
        'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
        (k, v)
    )

    conn.commit()
    conn.close()

init_db()

#=========================================================

#HELPERS

#=========================================================

def is_admin(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT user_id FROM admins WHERE
user_id=?',
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row is not None

def get_balance(user_id):
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT balance FROM users WHERE
user_id=?',
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

return row[0] if row else 0

def add_user(user_id):
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute(
    'INSERT OR IGNORE INTO users (user_id) VALUES (?)',
    (user_id,)
)

    conn.commit()
    conn.close()

def get_categories():
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute('SELECT name FROM categories')
    rows = cursor.fetchall()

    conn.close()

    return [x[0] for x in rows]

#=========================================================

#MAIN KEYBOARD

#=========================================================

def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

markup.row('📲 GET NUMBER', '💰 BALANCE')
markup.row('📦 STATUS', '👥 REFER')
markup.row('🛠 SUPPORT')

if is_admin(user_id):
    markup.row('⚙ ADMIN PANEL')

return markup

#=========================================================

#START

#=========================================================

@bot.message_handler(commands=['start']) def start(message): user_id = message.from_user.id add_user(user_id)

text = (
    '✅ *Welcome To Number Bot*\n\n'
    '⚡ Fast Delivery\n'
    '🔐 Secure Numbers\n'
    '📲 Instant Service'
)

bot.send_message(user_id, text, reply_markup=main_keyboard(user_id))

#=========================================================

#TEXT HANDLER

#=========================================================

@bot.message_handler(func=lambda m: True)
def text_handler(message):
    user_id = message.from_user.id
    text = message.text

if text == '💰 BALANCE':
    balance = get_balance(user_id)
    bot.send_message(user_id, f'💰 Your Balance: `{balance:.2f}$`')

elif text == '📦 STATUS':
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT category, country_flag, country_name, COUNT(*)
    FROM numbers
    WHERE status='available'
    GROUP BY category, country_name
    ''')

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(user_id, '❌ No stock available')
        return

    msg = '📦 *Available Stock*\n\n'

    for row in rows:
        msg += f'📌 {row[0]} | {row[1]} {row[2]} | {row[3]}\n'

    bot.send_message(user_id, msg)

elif text == '📲 GET NUMBER':
    categories = get_categories()

    if not categories:
        bot.send_message(user_id, '❌ No category found')
        return

    markup = types.InlineKeyboardMarkup()

    for cat in categories:
        markup.add(types.InlineKeyboardButton(text=f'📌 {cat}', callback_data=f'cat_{cat}'))

    bot.send_message(user_id, '📌 Select Service', reply_markup=markup)

elif text == '👥 REFER':
    me = bot.get_me()
    ref_link = f'https://t.me/{me.username}?start={user_id}'
    bot.send_message(user_id, f'👥 Your Referral Link:\n{ref_link}')

elif text == '🛠 SUPPORT':
    bot.send_message(user_id, '🛠 Contact Admin: @admin')

elif text == '⚙ ADMIN PANEL' and is_admin(user_id):
    admin_panel(user_id)

#=========================================================

#ADMIN PANEL

#=========================================================

def admin_panel(user_id): markup = types.InlineKeyboardMarkup(row_width=2)

markup.add(
    types.InlineKeyboardButton('➕ Add Category', callback_data='add_category'),
    types.InlineKeyboardButton('➕ Add Number', callback_data='add_number')
)

markup.add(types.InlineKeyboardButton('📋 All Numbers', callback_data='all_numbers'))

bot.send_message(user_id, '⚙ *Admin Panel*', reply_markup=markup)

#=========================================================

#CALLBACKS

#=========================================================

@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    user_id = call.from_user.id
    data = call.data

if data.startswith('cat_'):
    category = data.replace('cat_', '')

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT id, country_flag, country_name, phone_number, rate
    FROM numbers
    WHERE category=? AND status='available'
    LIMIT 1
    ''', (category,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        bot.answer_callback_query(call.id, 'No number available')
        return

    num_id = row[0]

    cursor.execute(
        '''
        UPDATE numbers
        SET status='assigned', assigned_to=?
        WHERE id=?
        ''',
        (user_id, num_id)
    )

    conn.commit()
    conn.close()

    text = (
        '✅ *Number Assigned*\n\n'
        f'🌍 Country: {row[1]} {row[2]}\n'
        f'📞 Number: `{row[3]}`\n'
        f'💵 Rate: `{row[4]}$`'
    )

    bot.edit_message_text(text, user_id, call.message.message_id)

elif data == 'add_category' and is_admin(user_id):
    msg = bot.send_message(user_id, 'Send category name:')
    bot.register_next_step_handler(msg, process_add_category)

elif data == 'add_number' and is_admin(user_id):
    msg = bot.send_message(user_id, 'Send:\ncategory,country,flag,number,rate')
    bot.register_next_step_handler(msg, process_add_number)

#=========================================================

#ADD CATEGORY

#=========================================================

def process_add_category(message):
    user_id = message.from_user.id

if not is_admin(user_id):
    return

name = message.text.strip()

conn = db_connect()
cursor = conn.cursor()

try:
    cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
    conn.commit()
    bot.send_message(user_id, '✅ Category Added')

except Exception as e:
    bot.send_message(user_id, f'❌ Error: {e}')

conn.close()

#=========================================================

#ADD NUMBER

#=========================================================

def process_add_number(message):
    user_id = message.from_user.id

if not is_admin(user_id):
    return

try:
    data = message.text.split(',')

    category = data[0].strip()
    country = data[1].strip()
    flag = data[2].strip()
    number = data[3].strip()
    rate = float(data[4].strip())

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute(
        '''
        INSERT INTO numbers (
            category,
            country_name,
            country_flag,
            phone_number,
            rate
        )
        VALUES (?, ?, ?, ?, ?)
        ''',
        (category, country, flag, number, rate)
    )

    conn.commit()
    conn.close()

    bot.send_message(user_id, '✅ Number Added')

except Exception as e:
    bot.send_message(user_id, f'❌ Error: {e}')

#=========================================================

#RUN BOT

#=========================================================

print('Bot Running...')
bot.infinity_polling(timeout=30, long_polling_timeout=30)
