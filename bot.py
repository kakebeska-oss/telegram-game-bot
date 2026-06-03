import asyncio
import sqlite3
from datetime import datetime, timedelta
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8868269079:AAFQsfowJYuL3OhAve85L_-KsmEKHaLRjHk"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

def get_db():
    return sqlite3.connect("/opt/render/project/src/bot.db")

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        balance REAL DEFAULT 100.0, total_earned REAL DEFAULT 0,
        total_lost REAL DEFAULT 0, games_played INTEGER DEFAULT 0,
        games_won INTEGER DEFAULT 0, last_bonus TEXT)''')
    conn.commit()
    conn.close()

def get_user(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    u = c.fetchone()
    conn.close()
    return u

def upd_bal(uid, amt, op="add"):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    if op == "add":
        c.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE user_id=?", (amt, amt, uid))
    else:
        c.execute("UPDATE users SET balance=balance-?, total_lost=total_lost+? WHERE user_id=?", (amt, amt, uid))
    conn.commit()
    conn.close()

def can_bonus(uid):
    u = get_user(uid)
    if u and u[8]:
        return datetime.now() - datetime.fromisoformat(u[8]) > timedelta(hours=24)
    return True

def set_bonus(uid):
    conn = get_db()
    conn.execute("UPDATE users SET last_bonus=? WHERE user_id=?", (datetime.now().isoformat(), uid))
    conn.commit()
    conn.close()

def get_top():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, username, balance FROM users ORDER BY balance DESC LIMIT 10")
    r = c.fetchall()
    conn.close()
    return r

def get_rank(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*)+1 FROM users WHERE balance>(SELECT balance FROM users WHERE user_id=?)", (uid,))
    r = c.fetchone()[0]
    conn.close()
    return r

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💰 Баланс", callback_data="bal"))
    kb.row(InlineKeyboardButton(text="🎮 Игры", callback_data="games"))
    kb.row(InlineKeyboardButton(text="🎁 Бонус", callback_data="bonus"))
    kb.row(InlineKeyboardButton(text="🏆 Рейтинг", callback_data="top"))
    kb.row(InlineKeyboardButton(text="📊 Стата", callback_data="stats"))
    return kb.as_markup()

def games_menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎲 Кости (x2)", callback_data="dice"))
    kb.row(InlineKeyboardButton(text="🪙 Орёл/Решка (x1.8)", callback_data="coin"))
    kb.row(InlineKeyboardButton(text="🎰 Слоты (x5)", callback_data="slots"))
    kb.row(InlineKeyboardButton(text="🎯 Угадай (x3)", callback_data="num"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back"))
    return kb.as_markup()

def again(g):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔄 Ещё", callback_data=g))
    kb.row(InlineKeyboardButton(text="🎮 Игры", callback_data="games"))
    kb.row(InlineKeyboardButton(text="🏠 Меню", callback_data="back"))
    return kb.as_markup()

@dp.message(Command("start"))
async def start(msg: types.Message):
    u = msg.from_user
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (u.id,))
    c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (u.username, u.first_name, u.id))
    conn.commit()
    conn.close()
    await msg.answer(f"🎮 Привет, {u.first_name}!\n💰 Старт: 100 монет", reply_markup=main_menu())

@dp.callback_query(F.data == "back")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("🎮 Меню:", reply_markup=main_menu())

@dp.callback_query(F.data == "bal")
async def bal(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    await call.message.edit_text(f"💰 Баланс: {u[3]:.1f}\n📊 Место: #{get_rank(call.from_user.id)}", reply_markup=main_menu())

@dp.callback_query(F.data == "bonus")
async def bonus(call: types.CallbackQuery):
    if not can_bonus(call.from_user.id):
        await call.answer("Уже забрал!", show_alert=True)
        return
    b = random.randint(10, 50)
    upd_bal(call.from_user.id, b)
    set_bonus(call.from_user.id)
    await call.message.edit_text(f"🎁 +{b}!\n💰 Баланс: {get_user(call.from_user.id)[3]:.1f}", reply_markup=main_menu())

@dp.callback_query(F.data == "top")
async def top(call: types.CallbackQuery):
    rows = get_top()
    txt = "🏆 ТОП-10:\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, r in enumerate(rows):
        name = r[1] or r[2] or str(r[0])
        m = medals[i] if i<3 else f"{i+1}."
        txt += f"{m} {name}: {r[3]:.0f}\n"
    txt += f"\n📊 Ты: #{get_rank(call.from_user.id)}"
    await call.message.edit_text(txt, reply_markup=main_menu())

@dp.callback_query(F.data == "stats")
async def stats(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    wr = (u[7]/u[6]*100) if u[6]>0 else 0
    txt = f"💰 {u[3]:.1f}\n📈 +{u[4]:.1f}\n📉 -{u[5]:.1f}\n🎮 Игр: {u[6]}\n✅ Побед: {u[7]}\n📊 WR: {wr:.1f}%"
    await call.message.edit_text(txt, reply_markup=main_menu())

@dp.callback_query(F.data == "games")
async def games(call: types.CallbackQuery):
    await call.message.edit_text("🎮 Игры:", reply_markup=games_menu())

# КОСТИ
@dp.callback_query(F.data == "dice")
async def dice_start(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    kb = InlineKeyboardBuilder()
    for b in [10,25,50,100]:
        kb.row(InlineKeyboardButton(text=f"🎲 {b}", callback_data=f"d_{b}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))
    await call.message.edit_text(f"🎲 КОСТИ\n💰 {u[3]:.1f}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("d_"))
async def dice_play(call: types.CallbackQuery):
    bet = int(call.data.split("_")[1])
    u = get_user(call.from_user.id)
    if u[3] < bet:
        await call.answer("Мало монет!", show_alert=True)
        return
    p,b = random.randint(1,6), random.randint(1,6)
    conn = get_db()
    conn.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (call.from_user.id,))
    if p>b:
        w=bet*2; upd_bal(call.from_user.id,w)
        conn.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (call.from_user.id,))
        res=f"🎉 +{w}"
    elif p==b:
        upd_bal(call.from_user.id,bet); res="🤝 Ничья"
    else:
        upd_bal(call.from_user.id,bet,"sub"); res=f"😢 -{bet}"
    conn.commit(); conn.close()
    await call.message.edit_text(f"🎲 Ты:{p} Бот:{b}\n{res}\n💰 {get_user(call.from_user.id)[3]:.1f}", reply_markup=again("dice"))

# ОРЁЛ/РЕШКА
@dp.callback_query(F.data == "coin")
async def coin_start(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    kb = InlineKeyboardBuilder()
    for b in [10,25,50,100]:
        kb.row(InlineKeyboardButton(text=f"🦅 Орёл {b}", callback_data=f"c_e_{b}"))
        kb.row(InlineKeyboardButton(text=f"🪙 Решка {b}", callback_data=f"c_t_{b}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))
    await call.message.edit_text(f"🪙 МОНЕТКА\n💰 {u[3]:.1f}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("c_"))
async def coin_play(call: types.CallbackQuery):
    _,ch,bet = call.data.split("_"); bet=int(bet)
    u = get_user(call.from_user.id)
    if u[3] < bet: await call.answer("Мало монет!", show_alert=True); return
    res = random.choice(["e","t"])
    conn = get_db()
    conn.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (call.from_user.id,))
    if ch==res:
        w=int(bet*1.8); upd_bal(call.from_user.id,w)
        conn.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (call.from_user.id,))
        txt=f"🎉 +{w}"
    else:
        upd_bal(call.from_user.id,bet,"sub"); txt=f"😢 -{bet}"
    conn.commit(); conn.close()
    r="ОРЁЛ" if res=="e" else "РЕШКА"
    await call.message.edit_text(f"🪙 {r}\n{txt}\n💰 {get_user(call.from_user.id)[3]:.1f}", reply_markup=again("coin"))

# СЛОТЫ
@dp.callback_query(F.data == "slots")
async def slots_start(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    kb = InlineKeyboardBuilder()
    for b in [10,25,50,100]:
        kb.row(InlineKeyboardButton(text=f"🎰 {b}", callback_data=f"s_{b}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))
    await call.message.edit_text(f"🎰 СЛОТЫ\n3= x5 | 2= x2\n💰 {u[3]:.1f}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def slots_play(call: types.CallbackQuery):
    bet = int(call.data.split("_")[1])
    u = get_user(call.from_user.id)
    if u[3] < bet: await call.answer("Мало монет!", show_alert=True); return
    sym=["🍒","🍋","🍊","7️⃣","💎","🌟"]
    a,b,c = random.choice(sym),random.choice(sym),random.choice(sym)
    conn = get_db()
    conn.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (call.from_user.id,))
    if a==b==c:
        w=bet*5; upd_bal(call.from_user.id,w)
        conn.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (call.from_user.id,))
        txt=f"🎉 ДЖЕКПОТ +{w}"
    elif a==b or b==c or a==c:
        w=bet*2; upd_bal(call.from_user.id,w)
        conn.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (call.from_user.id,))
        txt=f"🎊 +{w}"
    else:
        upd_bal(call.from_user.id,bet,"sub"); txt=f"😢 -{bet}"
    conn.commit(); conn.close()
    await call.message.edit_text(f"🎰 [{a}|{b}|{c}]\n{txt}\n💰 {get_user(call.from_user.id)[3]:.1f}", reply_markup=again("slots"))

# УГАДАЙ
@dp.callback_query(F.data == "num")
async def num_start(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    kb = InlineKeyboardBuilder()
    for b in [10,25,50]:
        kb.row(InlineKeyboardButton(text=f"🎯 {b}", callback_data=f"nb_{b}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="games"))
    await call.message.edit_text(f"🎯 УГАДАЙ 1-5\n💰 {u[3]:.1f}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("nb_"))
async def num_bet(call: types.CallbackQuery):
    bet = int(call.data.split("_")[1])
    kb = InlineKeyboardBuilder()
    for i in range(1,6):
        kb.row(InlineKeyboardButton(text=str(i), callback_data=f"ng_{bet}_{i}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="num"))
    await call.message.edit_text(f"Ставка: {bet}\nЧисло:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("ng_"))
async def num_play(call: types.CallbackQuery):
    _,bet,g = call.data.split("_"); bet,g=int(bet),int(g)
    u = get_user(call.from_user.id)
    if u[3] < bet: await call.answer("Мало монет!", show_alert=True); return
    c = random.randint(1,5)
    conn = get_db()
    conn.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (call.from_user.id,))
    if g==c:
        w=bet*3; upd_bal(call.from_user.id,w)
        conn.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (call.from_user.id,))
        txt=f"🎉 +{w}"
    else:
        upd_bal(call.from_user.id,bet,"sub"); txt=f"😢 -{bet} (было {c})"
    conn.commit(); conn.close()
    await call.message.edit_text(f"🎯 Ты:{g} | {c}\n{txt}\n💰 {get_user(call.from_user.id)[3]:.1f}", reply_markup=again("num"))

async def main():
    init_db()
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())