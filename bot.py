import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

# إعداد قاعدة البيانات المحلية لتتبع المهام المنجزة للمستخدمين
def init_db():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    # جدول لتسجيل المهام التي أتمها كل مستخدم
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tasks (
            user_id INTEGER,
            task_id TEXT,
            PRIMARY KEY (user_id, task_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# دالة التحقق مما إذا كانت المهمة قد انجزت مسبقاً
def has_completed_task(user_id: int, task_id: str) -> bool:
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM user_tasks WHERE user_id = ? AND task_id = ?', (user_id, task_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# دالة تسجيل إنجاز المهمة
def mark_task_completed(user_id: int, task_id: str):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO user_tasks (user_id, task_id) VALUES (?, ?)', (user_id, task_id))
    conn.commit()
    conn.close()

# أمر بدء المهمة وعرض زر التنفيذ
async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = "daily_task_1" # معرف فريد للمهمة

    # التحقق مسبقاً إذا أنجزها المستخدم
    if has_completed_task(user_id, task_id):
        await update.message.reply_text("لقد قمت بتنفيذ هذه المهمة مسبقاً ولا يمكنك إعادتها!")
        return

    keyboard = [[InlineKeyboardButton("✅ تنفيذ المهمة", callback_data=f"complete_{task_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("لديك مهمة جديدة، اضغط أدناه لتنفيذها:", reply_markup=reply_markup)

# معالجة الضغط على زر تنفيذ المهمة
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data

    if data.startswith("complete_"):
        task_id = data.split("_", 1)[1]

        # التحقق مرة أخرى أماناً لمنع الثغرات بالتزامن
        if has_completed_task(user_id, task_id):
            await query.edit_message_text(text="⚠️ لقد قمت بتنفيذ هذه المهمة من قبل بالفعل!")
            return

        # تسجيل إنجاز المهمة في قاعدة البيانات
        mark_task_completed(user_id, task_id)

        # منح المكافأة أو تنفيذ منطق المهمة هنا...
        
        # تعديل الرسالة وإزالة الزر لمنع الضغط عليه مرة أخرى
        await query.edit_message_text(text="🎉 تم تنفيذ المهمة بنجاح وتم تسجيلها!")

# إعداد التطبيق (تأكد من وضع توكن البوت الخاص بك)
app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

app.add_handler(CommandHandler("task", start_task))
app.add_handler(CallbackQueryHandler(button_handler))

if __name__ == "__main__":
    app.run_polling()
    
