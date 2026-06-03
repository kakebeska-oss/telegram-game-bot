import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Ваш токен от @BotFather
BOT_TOKEN = "8868269079:AAFQsfowJYuL3OhAve85L_-KsmEKHaLRjHk"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Константы
START_BALANCE = 100.0
DAILY_BONUS_MIN = 10
DAILY_BONUS_MAX = 50
MIN_BET = 5


# ============ РАБОТА С БАЗОЙ ДАННЫХ ============

class Database:
    def __init__(self, db_name="game_bot.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        """Создание всех таблиц"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 100.0,
                total_earned REAL DEFAULT 0,
                total_lost REAL DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                last_daily_bonus TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица для хранения версии бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute('''
            INSERT OR IGNORE INTO bot_info (key, value) 
            VALUES ('version', '1.0.0')
        ''')

        conn.commit()
        conn.close()

    def get_user(self, user_id):
        """Получить информацию о пользователе"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id) VALUES (?)
        ''', (user_id,))
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.commit()
        conn.close()
        return user

    def update_balance(self, user_id, amount, operation='add'):
        """Обновление баланса"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Убедимся что пользователь существует
        cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))

        if operation == 'add':
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    total_earned = total_earned + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, amount, user_id))
        else:
            cursor.execute('''
                UPDATE users 
                SET balance = balance - ?, 
                    total_lost = total_lost + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, amount, user_id))

        conn.commit()
        conn.close()

    def add_transaction(self, user_id, amount, type, description):
        """Добавление транзакции"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, type, description))
        conn.commit()
        conn.close()

    def get_top_players(self, limit=10):
        """Топ игроков по балансу"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, balance, total_earned
            FROM users 
            ORDER BY balance DESC 
            LIMIT ?
        ''', (limit,))
        top = cursor.fetchall()
        conn.close()
        return top

    def get_user_rank(self, user_id):
        """Узнать место пользователя в рейтинге"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) + 1 FROM users 
            WHERE balance > (SELECT balance FROM users WHERE user_id = ?)
        ''', (user_id,))
        rank = cursor.fetchone()[0]
        conn.close()
        return rank

    def can_get_daily_bonus(self, user_id):
        """Проверка можно ли получить ежедневный бонус"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_daily_bonus FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            last_bonus = datetime.fromisoformat(result[0])
            return datetime.now() - last_bonus > timedelta(hours=24)
        return True

    def set_daily_bonus(self, user_id):
        """Отметить получение ежедневного бонуса"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET last_daily_bonus = ? 
            WHERE user_id = ?
        ''', (datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()

    def transfer_money(self, from_user, to_user, amount):
        """Перевод денег между пользователями"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Проверка баланса отправителя
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (from_user,))
        sender_balance = cursor.fetchone()

        if not sender_balance or sender_balance[0] < amount:
            conn.close()
            return False

        # Списание у отправителя
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?',
                       (amount, from_user))

        # Начисление получателю
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id) VALUES (?)
        ''', (to_user,))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?',
                       (amount, to_user))

        conn.commit()
        conn.close()
        return True

    def get_user_stats(self, user_id):
        """Полная статистика пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT balance, total_earned, total_lost, games_played, games_won
            FROM users WHERE user_id = ?
        ''', (user_id,))
        stats = cursor.fetchone()
        conn.close()
        return stats


db = Database()


# ============ КЛАВИАТУРЫ ============

def get_main_keyboard():
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💰 Баланс", callback_data="balance"))
    builder.row(InlineKeyboardButton(text="🎮 Игры", callback_data="games"))
    builder.row(InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily"))
    builder.row(InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating"))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    builder.row(InlineKeyboardButton(text="💸 Перевод", callback_data="transfer"))
    builder.row(InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
    return builder.as_markup()


def get_games_keyboard():
    """Меню игр"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Кости (x2)", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="🪙 Орел/Решка (x1.8)", callback_data="game_coin"))
    builder.row(InlineKeyboardButton(text="🎰 Слоты (x5)", callback_data="game_slots"))
    builder.row(InlineKeyboardButton(text="🎯 Угадай число (x3)", callback_data="game_number"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def get_play_again_keyboard(game_type):
    """Клавиатура после игры"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Сыграть еще", callback_data=game_type))
    builder.row(InlineKeyboardButton(text="🎮 Другие игры", callback_data="games"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


# ============ ОБРАБОТЧИКИ КОМАНД ============

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user = db.get_user(message.from_user.id)

    # Обновляем информацию о пользователе
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET username = ?, first_name = ?
        WHERE user_id = ?
    ''', (message.from_user.username, message.from_user.first_name, message.from_user.id))
    conn.commit()
    conn.close()

    welcome_text = (
        f"🎮 Привет, {message.from_user.first_name}!\n\n"
        f"Добро пожаловать в игрового бота!\n"
        f"💰 Ваш стартовый баланс: {START_BALANCE} монет\n\n"
        f"🎲 Играй в мини-игры и увеличивай свой капитал!\n"
        f"🏆 Соревнуйся с другими игроками в рейтинге\n"
        f"🎁 Получай ежедневные бонусы\n\n"
        f"Выбери действие в меню:"
    )

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Быстрая проверка баланса"""
    user = db.get_user(message.from_user.id)
    rank = db.get_user_rank(message.from_user.id)
    await message.answer(
        f"💰 Ваш баланс: {user[3]:.1f} монет\n"
        f"📊 Место в рейтинге: #{rank}"
    )


# ============ CALLBACK ОБРАБОТЧИКИ ============

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    """Показать главное меню"""
    await callback.message.edit_text(
        "🎮 Главное меню\nВыберите действие:",
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "balance")
async def show_balance(callback: types.CallbackQuery):
    """Показать баланс"""
    user = db.get_user(callback.from_user.id)
    rank = db.get_user_rank(callback.from_user.id)

    await callback.message.edit_text(
        f"👤 Профиль: {callback.from_user.first_name}\n"
        f"💰 Баланс: {user[3]:.1f} монет\n"
        f"📊 Место в рейтинге: #{rank}\n"
        f"🎮 Сыграно игр: {user[6]}\n"
        f"📈 Всего выиграно: {user[4]:.1f}\n"
        f"📉 Всего проиграно: {user[5]:.1f}",
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "daily")
async def daily_bonus(callback: types.CallbackQuery):
    """Ежедневный бонус"""
    if not db.can_get_daily_bonus(callback.from_user.id):
        # Когда можно будет получить следующий бонус
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_daily_bonus FROM users WHERE user_id = ?',
                       (callback.from_user.id,))
        last_bonus = cursor.fetchone()
        conn.close()

        next_bonus = datetime.fromisoformat(last_bonus[0]) + timedelta(hours=24)
        wait_time = next_bonus - datetime.now()
        hours = int(wait_time.total_seconds() // 3600)
        minutes = int((wait_time.total_seconds() % 3600) // 60)

        await callback.answer(
            f"Бонус уже получен! Следующий через {hours}ч {minutes}мин",
            show_alert=True
        )
        return

    bonus = random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)
    db.update_balance(callback.from_user.id, bonus)
    db.set_daily_bonus(callback.from_user.id)
    db.add_transaction(callback.from_user.id, bonus, 'daily_bonus', 'Ежедневный бонус')

    await callback.message.edit_text(
        f"🎁 Вы получили ежедневный бонус: {bonus} монет!\n"
        f"💰 Текущий баланс: {db.get_user(callback.from_user.id)[3]:.1f} монет",
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "rating")
async def show_rating(callback: types.CallbackQuery):
    """Показать рейтинг игроков"""
    top_players = db.get_top_players(10)

    rating_text = "🏆 ТОП-10 ИГРОКОВ:\n\n"

    for i, player in enumerate(top_players, 1):
        name = player[2] or player[1] or f"ID:{player[0]}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        rating_text += f"{medal} {name}: {player[3]:.0f} монет\n"

    user_rank = db.get_user_rank(callback.from_user.id)
    rating_text += f"\n📊 Ваше место: #{user_rank}"

    await callback.message.edit_text(rating_text, reply_markup=get_main_keyboard())


@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    """Показать статистику"""
    stats = db.get_user_stats(callback.from_user.id)

    if stats[3] > 0:  # Если были игры
        winrate = (stats[4] / stats[3]) * 100
    else:
        winrate = 0

    stats_text = (
        f"📊 СТАТИСТИКА ИГРОКА\n"
        f"👤 {callback.from_user.first_name}\n\n"
        f"💰 Текущий баланс: {stats[0]:.1f}\n"
        f"📈 Всего заработано: {stats[1]:.1f}\n"
        f"📉 Всего проиграно: {stats[2]:.1f}\n"
        f"🎮 Сыграно игр: {stats[3]}\n"
        f"✅ Побед: {stats[4]}\n"
        f"📊 Процент побед: {winrate:.1f}%\n"
        f"💎 Чистая прибыль: {stats[1] - stats[2]:.1f}"
    )

    await callback.message.edit_text(stats_text, reply_markup=get_main_keyboard())


@dp.callback_query(F.data == "transfer")
async def transfer_menu(callback: types.CallbackQuery):
    """Меню перевода"""
    await callback.message.edit_text(
        "💸 Для перевода монет используйте команду:\n"
        "/transfer @username сумма\n\n"
        "Например: /transfer @friend 50",
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    """Помощь"""
    help_text = (
        "🎮 ПОМОЩЬ ПО БОТУ\n\n"
        "💰 Баланс - проверка вашего счета\n"
        "🎲 Игры - мини-игры для заработка\n"
        "🎁 Бонус - ежедневный бонус (раз в 24ч)\n"
        "🏆 Рейтинг - топ богатых игроков\n"
        "📊 Статистика - ваша игровая статистика\n"
        "💸 Перевод - отправить монеты другу\n\n"
        "🎯 Доступные игры:\n"
        "• Кости - брось кубик против бота\n"
        "• Орел/Решка - угадай сторону\n"
        "• Слоты - поймай удачу\n"
        "• Угадай число - выбери от 1 до 5\n\n"
        "❓ Вопросы? Пиши @your_support"
    )
    await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())


# ============ ИГРЫ ============

@dp.callback_query(F.data == "games")
async def show_games(callback: types.CallbackQuery):
    """Показать список игр"""
    await callback.message.edit_text(
        "🎮 ВЫБЕРИТЕ ИГРУ:\n\n"
        "🎲 Кости - ставка x2\n"
        "🪙 Орел/Решка - ставка x1.8\n"
        "🎰 Слоты - джекпот x5\n"
        "🎯 Угадай число - ставка x3",
        reply_markup=get_games_keyboard()
    )


@dp.callback_query(F.data == "game_dice")
async def game_dice_start(callback: types.CallbackQuery):
    """Начало игры в кости"""
    user = db.get_user(callback.from_user.id)

    # Клавиатура выбора ставки
    builder = InlineKeyboardBuilder()
    for bet in [10, 25, 50, 100]:
        builder.row(InlineKeyboardButton(
            text=f"🎲 {bet} монет",
            callback_data=f"dice_bet_{bet}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))

    await callback.message.edit_text(
        f"🎲 КОСТИ (шанс 50%)\n"
        f"💰 Ваш баланс: {user[3]:.1f}\n\n"
        f"Выберите ставку:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("dice_bet_"))
async def game_dice_play(callback: types.CallbackQuery):
    """Игра в кости"""
    bet = int(callback.data.split("_")[2])
    user = db.get_user(callback.from_user.id)

    if user[3] < bet:
        await callback.answer("Недостаточно монет!", show_alert=True)
        return

    player_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)

    # Обновляем статистику игр
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE user_id = ?',
                   (callback.from_user.id,))

    if player_dice > bot_dice:
        winnings = bet * 2
        db.update_balance(callback.from_user.id, winnings, 'add')
        cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE user_id = ?',
                       (callback.from_user.id,))
        result = f"🎉 ПОБЕДА! +{winnings} монет"
    elif player_dice == bot_dice:
        db.update_balance(callback.from_user.id, bet, 'add')  # возврат ставки
        result = "🤝 НИЧЬЯ! Ставка возвращена"
    else:
        db.update_balance(callback.from_user.id, bet, 'remove')
        result = f"😢 ПОРАЖЕНИЕ! -{bet} монет"

    conn.commit()
    conn.close()

    db.add_transaction(callback.from_user.id, bet, 'game_dice', result)

    new_balance = db.get_user(callback.from_user.id)[3]

    await callback.message.edit_text(
        f"🎲 КОСТИ\n\n"
        f"🎯 Ваш бросок: {player_dice}\n"
        f"🤖 Бросок бота: {bot_dice}\n\n"
        f"{result}\n"
        f"💰 Баланс: {new_balance:.1f} монет",
        reply_markup=get_play_again_keyboard("game_dice")
    )


@dp.callback_query(F.data == "game_coin")
async def game_coin_start(callback: types.CallbackQuery):
    """Начало игры Орел/Решка"""
    user = db.get_user(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    for bet in [10, 25, 50, 100]:
        builder.row(InlineKeyboardButton(
            text=f"🦅 Орел - {bet} монет",
            callback_data=f"coin_eagle_{bet}"
        ))
        builder.row(InlineKeyboardButton(
            text=f"🪙 Решка - {bet} монет",
            callback_data=f"coin_tails_{bet}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))

    await callback.message.edit_text(
        f"🪙 ОРЕЛ/РЕШКА (шанс 50%)\n"
        f"💰 Ваш баланс: {user[3]:.1f}\n\n"
        f"Выберите сторону и ставку:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("coin_"))
async def game_coin_play(callback: types.CallbackQuery):
    """Игра Орел/Решка"""
    parts = callback.data.split("_")
    choice = parts[1]  # eagle или tails
    bet = int(parts[2])

    user = db.get_user(callback.from_user.id)

    if user[3] < bet:
        await callback.answer("Недостаточно монет!", show_alert=True)
        return

    result = random.choice(["eagle", "tails"])
    result_text = "ОРЕЛ" if result == "eagle" else "РЕШКА"

    # Обновляем статистику
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE user_id = ?',
                   (callback.from_user.id,))

    if choice == result:
        winnings = int(bet * 1.8)
        db.update_balance(callback.from_user.id, winnings, 'add')
        cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE user_id = ?',
                       (callback.from_user.id,))
        game_result = f"🎉 ВЫИГРЫШ! +{winnings} монет"
    else:
        db.update_balance(callback.from_user.id, bet, 'remove')
        game_result = f"😢 ПРОИГРЫШ! -{bet} монет"

    conn.commit()
    conn.close()

    new_balance = db.get_user(callback.from_user.id)[3]

    await callback.message.edit_text(
        f"🪙 МОНЕТКА\n\n"
        f"Выпало: {result_text}\n"
        f"{game_result}\n"
        f"💰 Баланс: {new_balance:.1f} монет",
        reply_markup=get_play_again_keyboard("game_coin")
    )


@dp.callback_query(F.data == "game_slots")
async def game_slots_start(callback: types.CallbackQuery):
    """Начало игры Слоты"""
    user = db.get_user(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    for bet in [10, 25, 50, 100]:
        builder.row(InlineKeyboardButton(
            text=f"🎰 {bet} монет",
            callback_data=f"slots_bet_{bet}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))

    await callback.message.edit_text(
        f"🎰 СЛОТЫ\n"
        f"💰 Ваш баланс: {user[3]:.1f}\n\n"
        f"3 одинаковых = x5 к ставке!\n"
        f"2 одинаковых = x2 к ставке\n\n"
        f"Выберите ставку:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("slots_bet_"))
async def game_slots_play(callback: types.CallbackQuery):
    """Игра Слоты"""
    bet = int(callback.data.split("_")[2])
    user = db.get_user(callback.from_user.id)

    if user[3] < bet:
        await callback.answer("Недостаточно монет!", show_alert=True)
        return

    # Символы для слотов
    symbols = ["🍒", "🍋", "🍊", "7️⃣", "💎", "🌟"]

    # Крутим слоты
    slot1 = random.choice(symbols)
    slot2 = random.choice(symbols)
    slot3 = random.choice(symbols)

    # Проверяем комбинации
    if slot1 == slot2 == slot3:
        winnings = bet * 5
        result = "🎉 ДЖЕКПОТ! x5"
    elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
        winnings = bet * 2
        result = "🎊 ДВЕ ПАРЫ! x2"
    else:
        winnings = -bet
        result = "😢 НЕ ПОВЕЗЛО"

    # Обновляем баланс и статистику
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE user_id = ?',
                   (callback.from_user.id,))

    if winnings > 0:
        db.update_balance(callback.from_user.id, winnings, 'add')
        cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE user_id = ?',
                       (callback.from_user.id,))
    else:
        db.update_balance(callback.from_user.id, bet, 'remove')

    conn.commit()
    conn.close()

    new_balance = db.get_user(callback.from_user.id)[3]

    await callback.message.edit_text(
        f"🎰 СЛОТЫ\n\n"
        f"[ {slot1} | {slot2} | {slot3} ]\n\n"
        f"{result}\n"
        f"💰 Баланс: {new_balance:.1f} монет",
        reply_markup=get_play_again_keyboard("game_slots")
    )


@dp.callback_query(F.data == "game_number")
async def game_number_start(callback: types.CallbackQuery):
    """Начало игры Угадай число"""
    user = db.get_user(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    for bet in [10, 25, 50, 100]:
        builder.row(InlineKeyboardButton(
            text=f"🎯 {bet} монет",
            callback_data=f"number_bet_{bet}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))

    await callback.message.edit_text(
        f"🎯 УГАДАЙ ЧИСЛО (шанс 20%)\n"
        f"💰 Ваш баланс: {user[3]:.1f}\n\n"
        f"Угадайте число от 1 до 5\n"
        f"Приз: x3 от ставки!\n\n"
        f"Выберите ставку:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("number_bet_"))
async def game_number_bet(callback: types.CallbackQuery):
    """Выбор ставки для угадывания числа"""
    bet = int(callback.data.split("_")[2])

    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.row(InlineKeyboardButton(
            text=str(i),
            callback_data=f"number_guess_{bet}_{i}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="game_number"))

    await callback.message.edit_text(
        f"🎯 Выберите число от 1 до 5:\n"
        f"Ставка: {bet} монет",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("number_guess_"))
async def game_number_play(callback: types.CallbackQuery):
    """Игра Угадай число"""
    parts = callback.data.split("_")
    bet = int(parts[2])
    guess = int(parts[3])

    user = db.get_user(callback.from_user.id)

    if user[3] < bet:
        await callback.answer("Недостаточно монет!", show_alert=True)
        return

    correct_number = random.randint(1, 5)

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE user_id = ?',
                   (callback.from_user.id,))

    if guess == correct_number:
        winnings = bet * 3
        db.update_balance(callback.from_user.id, winnings, 'add')
        cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE user_id = ?',
                       (callback.from_user.id,))
        result = f"🎉 ВЫ УГАДАЛИ! +{winnings} монет"
    else:
        db.update_balance(callback.from_user.id, bet, 'remove')
        result = f"😢 НЕ УГАДАЛИ! -{bet} монет"

    conn.commit()
    conn.close()

    new_balance = db.get_user(callback.from_user.id)[3]

    await callback.message.edit_text(
        f"🎯 УГАДАЙ ЧИСЛО\n\n"
        f"Ваш выбор: {guess}\n"
        f"Правильное число: {correct_number}\n\n"
        f"{result}\n"
        f"💰 Баланс: {new_balance:.1f} монет",
        reply_markup=get_play_again_keyboard("game_number")
    )


# ============ ПЕРЕВОД МОНЕТ ============

@dp.message(Command("transfer"))
async def cmd_transfer(message: types.Message):
    """Перевод монет другому пользователю"""
    try:
        # Парсим команду /transfer @username сумма
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Неверный формат!\nИспользуйте: /transfer @username сумма")
            return

        username = parts[1].replace("@", "")
        amount = float(parts[2])

        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной!")
            return

        # Получаем ID получателя (упрощенно, нужно доработать)
        # В реальном боте нужно хранить username в БД и искать по нему
        await message.answer(
            "⚠️ Для перевода используйте меню бота.\n"
            "Функция в разработке."
        )

    except ValueError:
        await message.answer("❌ Неверная сумма! Используйте число.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ============ ЗАПУСК БОТА ============

async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())