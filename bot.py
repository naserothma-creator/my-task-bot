import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# =========================================================
# الإعدادات
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في Railway Variables")

if ADMIN_ID == 0:
    raise RuntimeError("ADMIN_ID غير موجود في Railway Variables")

DB_PATH = os.getenv("DB_PATH", "tasks.db")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================================================
# قاعدة البيانات
# =========================================================

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    reward REAL NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    proof_type TEXT,
    proof_file_id TEXT
)
""")

conn.commit()


# =========================================================
# الحالات
# =========================================================

class AddTask(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_reward = State()


class ProofState(StatesGroup):
    waiting_proof = State()


# =========================================================
# لوحات المفاتيح
# =========================================================

def user_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 المهام"),
                KeyboardButton(text="💰 رصيدي"),
            ],
            [
                KeyboardButton(text="🆔 معرفي"),
            ],
        ],
        resize_keyboard=True
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 المهام"),
                KeyboardButton(text="💰 رصيدي"),
            ],
            [
                KeyboardButton(text="🆔 معرفي"),
                KeyboardButton(text="🛠 لوحة التحكم"),
            ],
            [
                KeyboardButton(text="➕ إضافة مهمة"),
            ],
        ],
        resize_keyboard=True
    )


# =========================================================
# تسجيل المستخدم
# =========================================================

def register_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)",
        (user_id,)
    )
    conn.commit()


# =========================================================
# /start
# =========================================================

@dp.message(Command("start"))
async def start_command(message: types.Message):

    register_user(message.from_user.id)

    if message.from_user.id == ADMIN_ID:
        keyboard = admin_keyboard()
    else:
        keyboard = user_keyboard()

    await message.answer(
        f"أهلاً بك يا {message.from_user.first_name}! 👋\n\n"
        "مرحباً بك في بوت المهام والمكافآت 💰\n\n"
        "اختر أحد الأزرار من القائمة.",
        reply_markup=keyboard
    )


# =========================================================
# معرف المستخدم
# =========================================================

@dp.message(F.text == "🆔 معرفي")
async def my_id(message: types.Message):

    await message.answer(
        f"🆔 معرف Telegram الخاص بك:\n\n"
        f"`{message.from_user.id}`",
        parse_mode="Markdown"
    )


# =========================================================
# الرصيد
# =========================================================

@dp.message(F.text == "💰 رصيدي")
async def my_balance(message: types.Message):

    register_user(message.from_user.id)

    cursor.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )

    result = cursor.fetchone()

    balance = result[0] if result else 0

    await message.answer(
        f"💰 رصيدك الحالي:\n\n"
        f"**{balance:.2f}**",
        parse_mode="Markdown"
    )


# =========================================================
# عرض المهام
# =========================================================

@dp.message(F.text == "📋 المهام")
async def show_tasks(message: types.Message):

    cursor.execute(
        "SELECT id, title, description, reward FROM tasks ORDER BY id DESC"
    )

    tasks = cursor.fetchall()

    if not tasks:
        await message.answer(
            "📭 لا توجد مهام متاحة حالياً."
        )
        return

    await message.answer("📋 المهام المتاحة:")

    for task_id, title, description, reward in tasks:

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📤 تنفيذ المهمة",
                        callback_data=f"task_{task_id}"
                    )
                ]
            ]
        )

        await message.answer(
            f"📝 **{title}**\n\n"
            f"{description}\n\n"
            f"💰 المكافأة: **{reward:.2f}**",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# =========================================================
# اختيار مهمة
# =========================================================

@dp.callback_query(F.data.startswith("task_"))
async def select_task(
    callback: types.CallbackQuery,
    state: FSMContext
):

    task_id = int(callback.data.split("_")[1])

    cursor.execute(
        "SELECT title, description, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    if not task:
        await callback.answer(
            "المهمة غير موجودة.",
            show_alert=True
        )
        return

    title, description, reward = task

    # منع إرسال أكثر من إثبات لنفس المهمة وهي قيد المراجعة
    cursor.execute(
        """
        SELECT id FROM submissions
        WHERE user_id = ?
        AND task_id = ?
        AND status = 'pending'
        """,
        (callback.from_user.id, task_id)
    )

    if cursor.fetchone():
        await callback.answer(
            "لديك إثبات قيد المراجعة لهذه المهمة.",
            show_alert=True
        )
        return

    await state.update_data(task_id=task_id)

    await state.set_state(ProofState.waiting_proof)

    await callback.message.answer(
        f"📤 تنفيذ المهمة:\n\n"
        f"**{title}**\n\n"
        f"{description}\n\n"
        f"💰 المكافأة: **{reward:.2f}**\n\n"
        "أرسل الآن إثبات تنفيذ المهمة.\n"
        "يمكنك إرسال صورة 🖼️ أو ملف 📎.",
        parse_mode="Markdown"
    )

    await callback.answer()


# =========================================================
# استقبال إثبات بصورة
# =========================================================

@dp.message(
    ProofState.waiting_proof,
    F.photo
)
async def receive_photo_proof(
    message: types.Message,
    state: FSMContext
):

    data = await state.get_data()
    task_id = data.get("task_id")

    if not task_id:
        await state.clear()
        await message.answer("حدث خطأ. حاول اختيار المهمة مرة أخرى.")
        return

    file_id = message.photo[-1].file_id

    cursor.execute(
        """
        INSERT INTO submissions
        (user_id, task_id, status, proof_type, proof_file_id)
        VALUES (?, ?, 'pending', 'photo', ?)
        """,
        (
            message.from_user.id,
            task_id,
            file_id
        )
    )

    submission_id = cursor.lastrowid
    conn.commit()

    cursor.execute(
        "SELECT title, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    title = task[0]
    reward = task[1]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ قبول",
                    callback_data=f"approve_{submission_id}"
                ),
                InlineKeyboardButton(
                    text="❌ رفض",
                    callback_data=f"reject_{submission_id}"
                )
            ]
        ]
    )

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=(
            f"📨 إثبات مهمة جديد\n\n"
            f"👤 المستخدم: {message.from_user.full_name}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📝 المهمة: {title}\n"
            f"💰 المكافأة: {reward:.2f}\n"
            f"🔢 رقم الطلب: {submission_id}"
        ),
        reply_markup=keyboard
    )

    await message.answer(
        "✅ تم إرسال إثبات المهمة إلى المشرف.\n"
        "انتظر المراجعة."
    )

    await state.clear()


# =========================================================
# استقبال إثبات كملف
# =========================================================

@dp.message(
    ProofState.waiting_proof,
    F.document
)
async def receive_document_proof(
    message: types.Message,
    state: FSMContext
):

    data = await state.get_data()
    task_id = data.get("task_id")

    if not task_id:
        await state.clear()
        await message.answer("حدث خطأ. حاول اختيار المهمة مرة أخرى.")
        return

    file_id = message.document.file_id

    cursor.execute(
        """
        INSERT INTO submissions
        (user_id, task_id, status, proof_type, proof_file_id)
        VALUES (?, ?, 'pending', 'document', ?)
        """,
        (
            message.from_user.id,
            task_id,
            file_id
        )
    )

    submission_id = cursor.lastrowid
    conn.commit()

    cursor.execute(
        "SELECT title, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    title = task[0]
    reward = task[1]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ قبول",
                    callback_data=f"approve_{submission_id}"
                ),
                InlineKeyboardButton(
                    text="❌ رفض",
                    callback_data=f"reject_{submission_id}"
                )
            ]
        ]
    )

    await bot.send_document(
        chat_id=ADMIN_ID,
        document=file_id,
        caption=(
            f"📨 إثبات مهمة جديد\n\n"
            f"👤 المستخدم: {message.from_user.full_name}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📝 المهمة: {title}\n"
            f"💰 المكافأة: {reward:.2f}\n"
            f"🔢 رقم الطلب: {submission_id}"
        ),
        reply_markup=keyboard
    )

    await message.answer(
        "✅ تم إرسال إثبات المهمة إلى المشرف.\n"
        "انتظر المراجعة."
    )

    await state.clear()


# =========================================================
# إذا أرسل المستخدم نصاً بدل الإثبات
# =========================================================

@dp.message(ProofState.waiting_proof)
async def wrong_proof(message: types.Message):

    await message.answer(
        "⚠️ أرسل إثبات المهمة كصورة 🖼️ أو ملف 📎."
    )


# =========================================================
# قبول الإثبات
# =========================================================

@dp.callback_query(F.data.startswith("approve_"))
async def approve_submission(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "ليس لديك صلاحية.",
            show_alert=True
        )
        return

    submission_id = int(callback.data.split("_")[1])

    cursor.execute(
        """
        SELECT user_id, task_id, status
        FROM submissions
        WHERE id = ?
        """,
        (submission_id,)
    )

    submission = cursor.fetchone()

    if not submission:
        await callback.answer(
            "الطلب غير موجود.",
            show_alert=True
        )
        return

    user_id, task_id, status = submission

    if status != "pending":
        await callback.answer(
            "تمت معالجة هذا الطلب مسبقاً.",
            show_alert=True
        )
        return

    cursor.execute(
        "SELECT title, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    if not task:
        await callback.answer(
            "المهمة غير موجودة.",
            show_alert=True
        )
        return

    title, reward = task

    cursor.execute(
        "UPDATE submissions SET status = 'approved' WHERE id = ?",
        (submission_id,)
    )

    cursor.execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE user_id = ?
        """,
        (reward, user_id)
    )

    conn.commit()

    await bot.send_message(
        user_id,
        f"🎉 تم قبول مهمتك!\n\n"
        f"📝 المهمة: {title}\n"
        f"💰 تمت إضافة: {reward:.2f} إلى رصيدك."
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        f"✅ تم قبول الطلب رقم {submission_id}."
    )

    await callback.answer("تم القبول ✅")


# =========================================================
# رفض الإثبات
# =========================================================

@dp.callback_query(F.data.startswith("reject_"))
async def reject_submission(
    callback: types.CallbackQuery
):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "ليس لديك صلاحية.",
            show_alert=True
        )
        return

    submission_id = int(callback.data.split("_")[1])

    cursor.execute(
        """
        SELECT user_id, status
        FROM submissions
        WHERE id = ?
        """,
        (submission_id,)
    )

    submission = cursor.fetchone()

    if not submission:
        await callback.answer(
            "الطلب غير موجود.",
            show_alert=True
        )
        return

    user_id, status = submission

    if status != "pending":
        await callback.answer(
            "تمت معالجة هذا الطلب مسبقاً.",
            show_alert=True
        )
        return

    cursor.execute(
        "UPDATE submissions SET status = 'rejected' WHERE id = ?",
        (submission_id,)
    )

    conn.commit()

    await bot.send_message(
        user_id,
        "❌ تم رفض إثبات المهمة.\n\n"
        "يمكنك تنفيذ المهمة وإرسال إثبات جديد."
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        f"❌ تم رفض الطلب رقم {submission_id}."
    )

    await callback.answer("تم الرفض ❌")


# =========================================================
# لوحة تحكم المشرف
# =========================================================

@dp.message(F.text == "🛠 لوحة التحكم")
async def admin_panel(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ ليس لديك صلاحية.")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tasks")
    tasks_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE status = 'pending'"
    )
    pending_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE status = 'approved'"
    )
    approved_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE status = 'rejected'"
    )
    rejected_count = cursor.fetchone()[0]

    await message.answer(
        "🛠 **لوحة التحكم**\n\n"
        f"👥 المستخدمون: {users_count}\n"
        f"📝 المهام: {tasks_count}\n"
        f"⏳ قيد المراجعة: {pending_count}\n"
        f"✅ المهام المقبولة: {approved_count}\n"
        f"❌ المهام المرفوضة: {rejected_count}",
        parse_mode="Markdown"
    )


# =========================================================
# إضافة مهمة - البداية
# =========================================================

@dp.message(F.text == "➕ إضافة مهمة")
async def add_task_start(
    message: types.Message,
    state: FSMContext
):

    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ ليس لديك صلاحية.")
        return

    await state.set_state(AddTask.waiting_title)

    await message.answer(
        "➕ إضافة مهمة جديدة\n\n"
        "أرسل اسم المهمة:"
    )


# =========================================================
# اسم المهمة
# =========================================================

@dp.message(AddTask.waiting_title)
async def add_task_title(
    message: types.Message,
    state: FSMContext
):

    await state.update_data(title=message.text)

    await state.set_state(AddTask.waiting_description)

    await message.answer(
        "الآن أرسل وصف المهمة:"
    )


# =========================================================
# وصف المهمة
# =========================================================

@dp.message(AddTask.waiting_description)
async def add_task_description(
    message: types.Message,
    state: FSMContext
):

    await state.update_data(description=message.text)

    await state.set_state(AddTask.waiting_reward)

    await message.answer(
        "الآن أرسل قيمة المكافأة.\n\n"
        "مثال:\n"
        "10"
    )


# =========================================================
# مكافأة المهمة
# =========================================================

@dp.message(AddTask.waiting_reward)
async def add_task_reward(
    message: types.Message,
    state: FSMContext
):

    try:
        reward = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer(
            "⚠️ أرسل رقمًا صحيحًا للمكافأة.\n"
            "مثال: 10"
        )
        return

    if reward <= 0:
        await message.answer(
            "⚠️ المكافأة يجب أن تكون أكبر من صفر."
        )
        return

    data = await state.get_data()

    cursor.execute(
        """
        INSERT INTO tasks (title, description, reward)
        VALUES (?, ?, ?)
        """,
        (
            data["title"],
            data["description"],
            reward
        )
    )

    conn.commit()

    await state.clear()

    await message.answer(
        "✅ تمت إضافة المهمة بنجاح!\n\n"
        f"📝 {data['title']}\n"
        f"💰 المكافأة: {reward:.2f}",
        reply_markup=admin_keyboard()
    )


# =========================================================
# تشغيل البوت
# =========================================================

async def main():

    await bot.delete_webhook(drop_pending_updates=True)

    print("Bot is starting...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
