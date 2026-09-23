import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)

# قراءة المتغيرات البيئية بشكل مرن وآمن
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0")
ADMIN_ID = int(ADMIN_ID_RAW) if str(ADMIN_ID_RAW).isdigit() else 0

DB_PATH = os.getenv("DB_PATH", "tasks.db")

# التحقق من المتغيرات الأساسية
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في Railway Variables")

if ADMIN_ID == 0:
    raise RuntimeError("ADMIN_ID غير موجود أو غير صالح في Railway Variables")

# إعداد البوت والموزع
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ==================== قاعدة البيانات ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            reward INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            sub_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            proof TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== الحالات (FSM) ====================
class TaskState(StatesGroup):
    waiting_for_proof = State()

class AdminTaskState(StatesGroup):
    waiting_for_title = State()
    waiting_for_reward = State()

# ==================== لوحات المفاتيح ====================
def get_main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text="📋 المهام"), KeyboardButton(text="💰 رصيدي")],
        [KeyboardButton(text="🆔 معرفي")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="👑 لوحة الأدمن")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة مهمة جديدة", callback_data="add_task")],
        [InlineKeyboardButton(text="📋 مراجعة المهام المعلقة", callback_data="review_tasks")]
    ])

# ==================== الأوامر والمعالجات ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, balance) VALUES (?, ?, 0)", (user_id, username))
    conn.commit()
    conn.close()

    await message.answer(
        f"أهلاً بك يا {message.from_user.first_name} N! 👋\n\nمرحباً بك في بوت المهام والمكافآت 💰\nاختر أحد الأزرار من القائمة.",
        reply_markup=get_main_keyboard(user_id)
    )

@router.message(F.text == "🆔 معرفي")
async def show_my_id(message: Message):
    await message.answer(f"🆔 معرف Telegram الخاص بك:\n\n`{message.from_user.id}`", parse_mode="Markdown")

@router.message(F.text == "💰 رصيدي")
async def show_balance(message: Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    balance = row[0] if row else 0
    await message.answer(f"💰 رصيدك الحالي هو: **{balance}** نقطة.", parse_mode="Markdown")

@router.message(F.text == "👑 لوحة الأدمن")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("عذراً، هذا الأمر مخصص للمشرف فقط.")
        return
    await message.answer("👑 أهلاً بك في لوحة تحكم المشرف:", reply_markup=get_admin_keyboard())

# ==================== نظام إضافة المهام (أدمن) ====================
@router.callback_query(F.data == "add_task")
async def start_add_task(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مسموح لك!", show_alert=True)
        return
    await callback.message.answer("أرسل عنوان المهمة أو وصفها:")
    await state.set_state(AdminTaskState.waiting_for_title)
    await callback.answer()

@router.message(AdminTaskState.waiting_for_title)
async def process_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("أرسل مكافأة هذه المهمة (رقم فقط، مثلاً: 50):")
    await state.set_state(AdminTaskState.waiting_for_reward)

@router.message(AdminTaskState.waiting_for_reward)
async def process_task_reward(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("الرجاء إدخال رقم صحيح للمكافأة:")
        return
    
    reward = int(message.text)
    data = await state.get_data()
    title = data['title']
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title, reward) VALUES (?, ?)", (title, reward))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ تمت إضافة المهمة بنجاح!", reply_markup=get_main_keyboard(message.from_user.id))

# ==================== عرض المهام للمستخدمين ====================
@router.message(F.text == "📋 المهام")
async def list_tasks(message: Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, title, reward FROM tasks")
    tasks = cursor.fetchall()
    conn.close()
    
    if not tasks:
        await message.answer("📭 لا توجد مهام متاحة حالياً.")
        return
    
    for task_id, title, reward in tasks:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="تنفيذ المهمة 🚀", callback_data=f"do_task_{task_id}")]
        ])
        await message.answer(f"📌 **{title}**\n💰 المكافأة: {reward} نقطة", parse_mode="Markdown", reply_markup=kb)

# تم تعديل هذا الجزء لضمان التقاط ضغطة زر المهمة والانتقال للحالة بدقة
@router.callback_query(F.data.startswith("do_task_"))
async def start_do_task(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[2])
        await state.update_data(task_id=task_id)
        await state.set_state(TaskState.waiting_for_proof)
        await callback.message.answer("📥 أرسل الآن إثبات إتمام المهمة (صورة، رابط، أو نص):")
    except Exception as e:
        logging.error(f"Error in do_task: {e}")
    finally:
        await callback.answer()

@router.message(TaskState.waiting_for_proof)
async def receive_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get('task_id')
    
    if not task_id:
        await message.answer("حدث خطأ يرجى اختيار المهمة من جديد عبر زر (📋 المهام).")
        await state.clear()
        return

    proof = message.text or message.caption or "إثبات مرفق"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO submissions (user_id, task_id, proof, status) VALUES (?, ?, ?, 'pending')", 
                   (message.from_user.id, task_id, proof))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer("✅ تم إرسال إثبات المهمة بنجاح وسيتم مراجعته من قبل المشرف قريباً.", reply_markup=get_main_keyboard(message.from_user.id))

# ==================== مراجعة المهام (أدمن) ====================
@router.callback_query(F.data == "review_tasks")
async def review_tasks(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مسموح لك!", show_alert=True)
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.sub_id, s.user_id, t.title, s.proof, t.reward 
        FROM submissions s 
        JOIN tasks t ON s.task_id = t.task_id 
        WHERE s.status = 'pending'
    """)
    subs = cursor.fetchall()
    conn.close()
    
    if not subs:
        await callback.message.answer("📭 لا توجد مهام معلقة للمراجعة.")
        await callback.answer()
        return
        
    for sub_id, user_id, title, proof, reward in subs:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ قبول", callback_data=f"accept_{sub_id}_{user_id}_{reward}"),
                InlineKeyboardButton(text="❌ رفض", callback_data=f"reject_{sub_id}")
            ]
        ])
        await callback.message.answer(
            f"📥 **مهمة مقدمة للمراجعة**\n\n👤 المستخدم: `{user_id}`\n📌 المهمة: {title}\n💬 الإثبات: {proof}\n💰 المكافأة: {reward}",
            parse_mode="Markdown", reply_markup=kb
        )
    await callback.answer()

@router.callback_query(F.data.startswith("accept_"))
async def accept_submission(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    parts = callback.data.split("_")
    sub_id = int(parts[1])
    user_id = int(parts[2])
    reward = int(parts[3])
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE submissions SET status = 'accepted' WHERE sub_id = ?", (sub_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"{callback.message.text}\n\n✅ **تم القبول وإضافة {reward} نقطة للمستخدم.**", parse_mode="Markdown")
    try:
        await bot.send_message(user_id, f"🎉 مبروك! تمت الموافقة على إنجازك للمهمة وحصلت على {reward} نقطة.")
    except:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_submission(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    sub_id = int(callback.data.split("_")[1])
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE submissions SET status = 'rejected' WHERE sub_id = ?", (sub_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(f"{callback.message.text}\n\n❌ **تم رفض المهمة.**", parse_mode="Markdown")
    await callback.answer()

# ==================== تشغيل البوت ====================
async def main():
    print("Bot is starting...")
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
        
