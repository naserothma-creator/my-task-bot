import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)


# =========================================================
# الإعدادات
# =========================================================

import os

API_TOKEN = os.getenv("BOT_TOKEN")


ADMIN_ID = 8672813301

DATABASE = "tasks.db"


# =========================================================
# إعداد التسجيل
# =========================================================

logging.basicConfig(level=logging.INFO)


# =========================================================
# قاعدة البيانات
# =========================================================

conn = sqlite3.connect(DATABASE)
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
    status TEXT DEFAULT 'pending'
)
""")


conn.commit()


# =========================================================
# البوت
# =========================================================

bot = Bot(token=API_TOKEN)

dp = Dispatcher(storage=MemoryStorage())


# =========================================================
# حالات إضافة المهمة
# =========================================================

class AddTask(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_reward = State()


# =========================================================
# حالات إرسال الإثبات
# =========================================================

class ProofState(StatesGroup):
    waiting_proof = State()


# =========================================================
# لوحة المستخدم
# =========================================================

def user_keyboard():

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 المهام"),
                KeyboardButton(text="💰 رصيدي")
            ],
            [
                KeyboardButton(text="🆔 معرفي")
            ]
        ],
        resize_keyboard=True
    )

    return keyboard


# =========================================================
# لوحة الأدمن
# =========================================================

def admin_keyboard():

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 المهام"),
                KeyboardButton(text="💰 رصيدي")
            ],
            [
                KeyboardButton(text="➕ إضافة مهمة"),
                KeyboardButton(text="🆔 معرفي")
            ],
            [
                KeyboardButton(text="🛠 لوحة التحكم")
            ]
        ],
        resize_keyboard=True
    )

    return keyboard


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

    user_id = message.from_user.id

    register_user(user_id)

    if user_id == ADMIN_ID:

        await message.answer(
            "👋 أهلاً بك يا أدمن\n\n"
            "تم تشغيل لوحة الإدارة الخاصة بك.",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "👋 أهلاً بك في بوت المهام 🤖\n\n"
            "يمكنك تنفيذ المهام وإرسال الإثبات للحصول على المكافآت.",
            reply_markup=user_keyboard()
        )


# =========================================================
# معرف المستخدم
# =========================================================

@dp.message(F.text == "🆔 معرفي")
async def my_id(message: types.Message):

    await message.answer(
        f"🆔 معرف حسابك:\n\n"
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
        f"💵 {balance:.2f}"
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

        text = (
            f"📝 <b>{title}</b>\n\n"
            f"📄 الوصف:\n{description}\n\n"
            f"💰 المكافأة: {reward:.2f}"
        )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )


# =========================================================
# اختيار مهمة
# =========================================================

@dp.callback_query(F.data.startswith("task_"))
async def select_task(callback: types.CallbackQuery, state: FSMContext):

    task_id = int(callback.data.split("_")[1])

    cursor.execute(
        "SELECT title, description, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    if not task:

        await callback.answer(
            "❌ هذه المهمة غير موجودة.",
            show_alert=True
        )

        return

    title, description, reward = task

    await state.update_data(task_id=task_id)

    await state.set_state(ProofState.waiting_proof)

    await callback.message.answer(
        f"📤 اخترت المهمة:\n\n"
        f"📝 {title}\n\n"
        f"💰 المكافأة: {reward:.2f}\n\n"
        f"أرسل الآن إثبات تنفيذ المهمة.\n\n"
        f"يمكنك إرسال:\n"
        f"🖼 صورة\n"
        f"📎 ملف\n\n"
        f"بعد الإرسال سيتم تحويل الإثبات إلى الإدارة للمراجعة."
    )

    await callback.answer()


# =========================================================
# استقبال صورة الإثبات
# =========================================================

@dp.message(ProofState.waiting_proof, F.photo)
async def receive_photo(message: types.Message, state: FSMContext):

    data = await state.get_data()

    task_id = data.get("task_id")

    if not task_id:

        await message.answer("❌ حدث خطأ، حاول مرة أخرى.")

        await state.clear()

        return

    user_id = message.from_user.id

    cursor.execute(
        """
        INSERT INTO submissions (user_id, task_id, status)
        VALUES (?, ?, 'pending')
        """,
        (user_id, task_id)
    )

    submission_id = cursor.lastrowid

    conn.commit()

    cursor.execute(
        "SELECT title, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    if not task:

        await message.answer("❌ المهمة غير موجودة.")

        await state.clear()

        return

    title, reward = task

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

    caption = (
        "📨 <b>إثبات مهمة جديد</b>\n\n"
        f"👤 المستخدم: <code>{user_id}</code>\n"
        f"📝 المهمة: {title}\n"
        f"💰 المكافأة: {reward:.2f}\n"
        f"🆔 رقم الطلب: {submission_id}"
    )

    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await message.answer(
        "✅ تم إرسال الإثبات إلى الإدارة.\n\n"
        "⏳ انتظر حتى تتم مراجعة المهمة."
    )

    await state.clear()


# =========================================================
# استقبال ملف الإثبات
# =========================================================

@dp.message(ProofState.waiting_proof, F.document)
async def receive_document(message: types.Message, state: FSMContext):

    data = await state.get_data()

    task_id = data.get("task_id")

    if not task_id:

        await message.answer("❌ حدث خطأ، حاول مرة أخرى.")

        await state.clear()

        return

    user_id = message.from_user.id

    cursor.execute(
        """
        INSERT INTO submissions (user_id, task_id, status)
        VALUES (?, ?, 'pending')
        """,
        (user_id, task_id)
    )

    submission_id = cursor.lastrowid

    conn.commit()

    cursor.execute(
        "SELECT title, reward FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    if not task:

        await message.answer("❌ المهمة غير موجودة.")

        await state.clear()

        return

    title, reward = task

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

    caption = (
        "📨 <b>إثبات مهمة جديد</b>\n\n"
        f"👤 المستخدم: <code>{user_id}</code>\n"
        f"📝 المهمة: {title}\n"
        f"💰 المكافأة: {reward:.2f}\n"
        f"🆔 رقم الطلب: {submission_id}"
    )

    await bot.send_document(
        ADMIN_ID,
        message.document.file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await message.answer(
        "✅ تم إرسال الإثبات إلى الإدارة.\n\n"
        "⏳ انتظر حتى تتم مراجعة المهمة."
    )

    await state.clear()


# =========================================================
# إذا أرسل المستخدم شيئاً غير صورة أو ملف
# =========================================================

@dp.message(ProofState.waiting_proof)
async def wrong_proof(message: types.Message):

    await message.answer(
        "⚠️ أرسل إثبات المهمة كصورة 🖼 أو ملف 📎."
    )


# =========================================================
# قبول الإثبات
# =========================================================

@dp.callback_query(F.data.startswith("approve_"))
async def approve_submission(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ ليس لديك صلاحية.",
            show_alert=True
        )

        return

    submission_id = int(
        callback.data.split("_")[1]
    )

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
            "❌ الطلب غير موجود.",
            show_alert=True
        )

        return

    user_id, task_id, status = submission

    if status != "pending":

        await callback.answer(
            "⚠️ تمت معالجة هذا الطلب مسبقاً.",
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
            "❌ المهمة غير موجودة.",
            show_alert=True
        )

        return

    title, reward = task

    cursor.execute(
        """
        UPDATE submissions
        SET status = 'approved'
        WHERE id = ?
        """,
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

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        f"✅ تم قبول المهمة رقم {submission_id}\n\n"
        f"👤 المستخدم: {user_id}\n"
        f"📝 المهمة: {title}\n"
        f"💰 تمت إضافة {reward:.2f} إلى رصيد المستخدم."
    )

    try:

        await bot.send_message(
            user_id,
            f"🎉 تم قبول مهمتك!\n\n"
            f"📝 المهمة: {title}\n"
            f"💰 المكافأة: {reward:.2f}\n\n"
            f"تمت إضافة المكافأة إلى رصيدك 💰"
        )

    except Exception as e:

        logging.error(
            f"Error sending approval message: {e}"
        )

    await callback.answer(
        "✅ تم قبول المهمة."
    )


# =========================================================
# رفض الإثبات
# =========================================================

@dp.callback_query(F.data.startswith("reject_"))
async def reject_submission(callback: types.CallbackQuery):

    if callback.from_user.id != ADMIN_ID:

        await callback.answer(
            "❌ ليس لديك صلاحية.",
            show_alert=True
        )

        return

    submission_id = int(
        callback.data.split("_")[1]
    )

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
            "❌ الطلب غير موجود.",
            show_alert=True
        )

        return

    user_id, task_id, status = submission

    if status != "pending":

        await callback.answer(
            "⚠️ تمت معالجة هذا الطلب مسبقاً.",
            show_alert=True
        )

        return

    cursor.execute(
        "SELECT title FROM tasks WHERE id = ?",
        (task_id,)
    )

    task = cursor.fetchone()

    title = task[0] if task else "مهمة"

    cursor.execute(
        """
        UPDATE submissions
        SET status = 'rejected'
        WHERE id = ?
        """,
        (submission_id,)
    )

    conn.commit()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        f"❌ تم رفض المهمة رقم {submission_id}\n\n"
        f"👤 المستخدم: {user_id}\n"
        f"📝 المهمة: {title}"
    )

    try:

        await bot.send_message(
            user_id,
            f"❌ تم رفض إثبات المهمة.\n\n"
            f"📝 المهمة: {title}\n\n"
            f"يمكنك تنفيذ المهمة مرة أخرى وإرسال إثبات واضح."
        )

    except Exception as e:

        logging.error(
            f"Error sending rejection message: {e}"
        )

    await callback.answer(
        "❌ تم رفض المهمة."
    )


# =========================================================
# إضافة مهمة - البداية
# =========================================================

@dp.message(F.text == "➕ إضافة مهمة")
async def add_task_start(message: types.Message, state: FSMContext):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "❌ ليس لديك صلاحية استخدام هذا الخيار."
        )

        return

    await state.set_state(
        AddTask.waiting_title
    )

    await message.answer(
        "➕ إضافة مهمة جديدة\n\n"
        "الخطوة 1️⃣\n\n"
        "أرسل اسم المهمة.\n\n"
        "مثال:\n"
        "📱 تحميل تطبيق"
    )


# =========================================================
# اسم المهمة
# =========================================================

@dp.message(AddTask.waiting_title)
async def add_task_title(
    message: types.Message,
    state: FSMContext
):

    title = message.text.strip()

    if len(title) < 2:

        await message.answer(
            "⚠️ اسم المهمة قصير جداً.\n"
            "أرسل اسماً واضحاً."
        )

        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        AddTask.waiting_description
    )

    await message.answer(
        "✅ تم حفظ اسم المهمة.\n\n"
        "الخطوة 2️⃣\n\n"
        "أرسل وصف المهمة بالتفصيل.\n\n"
        "مثال:\n"
        "قم بتحميل التطبيق ثم افتحه وأرسل صورة تثبت إتمام المهمة."
    )


# =========================================================
# وصف المهمة
# =========================================================

@dp.message(AddTask.waiting_description)
async def add_task_description(
    message: types.Message,
    state: FSMContext
):

    description = message.text.strip()

    if len(description) < 2:

        await message.answer(
            "⚠️ الوصف قصير جداً.\n"
            "أرسل وصفاً واضحاً."
        )

        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        AddTask.waiting_reward
    )

    await message.answer(
        "✅ تم حفظ الوصف.\n\n"
        "الخطوة 3️⃣\n\n"
        "أرسل قيمة المكافأة فقط.\n\n"
        "مثال:\n"
        "5\n\n"
        "أو:\n"
        "10.5"
    )


# =========================================================
# مكافأة المهمة
# =========================================================

@dp.message(AddTask.waiting_reward)
async def add_task_reward(
    message: types.Message,
    state: FSMContext
):

    reward_text = message.text.strip()

    try:

        reward = float(reward_text)

    except ValueError:

        await message.answer(
            "❌ المكافأة يجب أن تكون رقماً.\n\n"
            "مثال:\n"
            "5\n"
            "10\n"
            "2.5"
        )

        return

    if reward <= 0:

        await message.answer(
            "❌ المكافأة يجب أن تكون أكبر من صفر."
        )

        return

    data = await state.get_data()

    title = data["title"]
    description = data["description"]

    cursor.execute(
        """
        INSERT INTO tasks (title, description, reward)
        VALUES (?, ?, ?)
        """,
        (title, description, reward)
    )

    conn.commit()

    task_id = cursor.lastrowid

    await state.clear()

    await message.answer(
        "✅ تمت إضافة المهمة بنجاح!\n\n"
        f"🆔 رقم المهمة: {task_id}\n"
        f"📝 الاسم: {title}\n"
        f"📄 الوصف: {description}\n"
        f"💰 المكافأة: {reward:.2f}",
        reply_markup=admin_keyboard()
    )


# =========================================================
# لوحة التحكم
# =========================================================

@dp.message(F.text == "🛠 لوحة التحكم")
async def admin_panel(message: types.Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "❌ ليس لديك صلاحية."
        )

        return

    cursor.execute(
        "SELECT COUNT(*) FROM users")
    
    

    users_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM tasks")
    
    
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    
