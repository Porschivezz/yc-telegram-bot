import logging
import sqlite3
import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters
)
import openai

# --- Configuration ---
BOT_TOKEN = "7772445224:AAFHtxgxz9YcV334hYsjzOdsPk4k48uyq3M"
OPENAI_API_KEY = "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"
PAYMENT_PROVIDER_TOKEN = "381764678:TEST:121523"
PRICE_AMOUNT = 9900  # 99 RUB
CURRENCY = "RUB"

# Set OpenAI key and proxy
openai.api_key = OPENAI_API_KEY
openai.proxy = {
    "http":  "http://vmhprefy:s7jox1i8odvc@p.webshare.io:80",
    "https": "http://vmhprefy:s7jox1i8odvc@p.webshare.io:80",
}

# Free usage limit: 100 minutes = 6000 seconds
FREE_LIMIT = 100 * 60

# Prompts for initial tasks
TASK_PROMPTS = {
    "task_1": (
        "You are a meticulous copy editor. Your job is to correct all spelling, grammar, punctuation, and capitalization errors. Preserve the original meaning, terminology and author’s tone of voice. Do not add, remove or rephrase any content beyond essential corrections. However, if you see any wrong spelling of words then always correct it. This is important! Always correct any mistakes in spelling, grammar or punctuation in the original language! For example if you see a word тарилочка, then correct it for тарелочка. This is important! Output only the corrected text, without any commentary or explanation."
    ),
    "task_2": (
        "You are a concise style rewriter. Given the provided text, produce a clear, well-structured message that: 1. Retains the original tone and intent. 2. Focuses on the main ideas; remove redundant or off-topic details. 3. Uses short paragraphs or bullet points if it improves readability. 4. Keeps the length to approximately 30–50% of the original. Output only the rewritten text, without labels or commentary."
    ),
    "task_3": (
        "You are a summarization specialist. From the given text, extract and list: The 3–7 key theses or arguments, each as a single bullet point. A brief overall summary (2–3 sentences) that captures the core message. Use consistent formatting (e.g., bullet points) and do not include any additional analysis."
    ),
}

# --- Database setup ---
conn = sqlite3.connect("subscriptions.db", check_same_thread=False)
c = conn.cursor()
c.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        used_seconds INTEGER NOT NULL DEFAULT 0,
        subscribed INTEGER NOT NULL DEFAULT 0
    )
    """
)
conn.commit()

# --- Helpers ---
def is_subscribed(user_id: int) -> bool:
    c.execute("SELECT subscribed FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return bool(row and row[0])

def get_used_seconds(user_id: int) -> int:
    c.execute("SELECT used_seconds FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else 0

def add_used_seconds(user_id: int, secs: int) -> None:
    prev = get_used_seconds(user_id)
    total = prev + secs
    c.execute(
        "INSERT INTO users(user_id, used_seconds) VALUES(?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET used_seconds=excluded.used_seconds",
        (user_id, total)
    )
    conn.commit()

def set_subscribed(user_id: int, value: bool) -> None:
    c.execute(
        "INSERT INTO users(user_id, used_seconds, subscribed) VALUES(?, 0, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET subscribed=excluded.subscribed",
        (user_id, int(value))
    )
    conn.commit()

# --- Bot Menus ---
async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Расшифровка (орфография)", callback_data="task_1")],
        [InlineKeyboardButton("Качественное сообщение", callback_data="task_2")],
        [InlineKeyboardButton("Создать тезисы", callback_data="task_3")],
    ]
    text = "Выберите действие:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"🎤 <b>Добро пожаловать!</b> Я — умный аудио-ассистент.\n"
        f"📢 <b>Что я умею:</b>\n"
        f"• Расшифровывать голосовые сообщения.\n"
        f"• Генерировать готовые сообщения.\n"
        f"• Создавать тезисы.\n\n"
        f"🔓 <b>{FREE_LIMIT//60} минут аудио бесплатно!</b>\n"
        f"💳 Оформить безлимит: /subscribe"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = f"sub_{update.effective_user.id}"
    prices = [LabeledPrice("Месячная подписка — 99 ₽", PRICE_AMOUNT)]
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Подписка на бота",
        description="Безлимитный доступ на месяц за 99 ₽",
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=prices
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_subscribed(update.effective_user.id, True)
    await update.message.reply_text("Спасибо за оплату! Подписка активирована.")

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    duration = 0
    if update.message.voice:
        duration = update.message.voice.duration
        context.user_data["file_id"] = update.message.voice.file_id
    elif update.message.audio:
        duration = update.message.audio.duration
        context.user_data["file_id"] = update.message.audio.file_id

    if not is_subscribed(user_id):
        used = get_used_seconds(user_id)
        if used + duration <= FREE_LIMIT:
            add_used_seconds(user_id, duration)
        else:
            await update.message.reply_text(
                f"Бесплатный лимит в {FREE_LIMIT//60} мин. исчерпан (использовано {used//60} мин.)\n"
                "Оформите подписку: /subscribe"
            )
            return
    context.user_data["audio_duration"] = duration
    await audio_menu(update, context)

async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.error import BadRequest
    query = update.callback_query
    await query.answer()
    task_type = query.data

    file_id = context.user_data.get("file_id")
    if not file_id:
        try:
            await query.edit_message_text("Файл не найден.")
        except BadRequest:
            pass
        return

    async def transcribe():
        file = await context.bot.get_file(file_id)
        path = f"{file_id}.ogg"
        await file.download_to_drive(path)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: openai.Audio.transcribe(model="whisper-1", file=open(path, "rb"))
        )
        return result.get("text", "")

    trans_task = asyncio.create_task(transcribe())
    estimated = max(context.user_data.get("audio_duration", 1), 1)
    prev_pct = -1
    for i in range(1, estimated + 1):
        if trans_task.done():
            break
        pct = int(i / estimated * 100)
        if pct != prev_pct:
            try:
                await query.edit_message_text(f"Обработка: {pct}%")
            except BadRequest:
                pass
            prev_pct = pct
        await asyncio.sleep(1)

    raw_text = await trans_task
    system_prompt = TASK_PROMPTS.get(task_type)
    if system_prompt:
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        result_text = completion.choices[0].message.content.strip()
    else:
        result_text = raw_text

    context.user_data["last_text"] = result_text
    try:
        await query.edit_message_text("Обработка: 100%")
    except BadRequest:
        pass

    keyboard = [
        [InlineKeyboardButton("Отправить результат", switch_inline_query_current_chat=result_text)],
        [InlineKeyboardButton("Сделать лаконичнее", callback_data="action_shorten")],
        [InlineKeyboardButton("Переписать в официально-деловом стиле", callback_data="action_official")],
        [InlineKeyboardButton("Переписать в неформальном стиле", callback_data="action_informal")],
        [InlineKeyboardButton("Обратно в меню", callback_data="action_reset")],
    ]
    await query.edit_message_text(result_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data
    text = context.user_data.get("last_text", "")
    if action == "action_reset":
        await audio_menu(update, context)
        return

    prompts = {
        "action_shorten": "You shorten the message preserving key ideas.",
        "action_official": "You rewrite the message in a formal business style preserving key ideas.",
        "action_informal": "You rewrite the message in a relaxed friendly style preserving key ideas.",
    }
    system_prompt = prompts.get(action, prompts["action_shorten"])
    completion = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        max_tokens=1000,
        temperature=0.7
    )
    res = completion.choices[0].message.content.strip()
    context.user_data["last_text"] = res

    keyboard = [
        [InlineKeyboardButton("Отправить результат", switch_inline_query_current_chat=res)],
        [InlineKeyboardButton("Сделать лаконичнее", callback_data="action_shorten")],
        [InlineKeyboardButton("Переписать в официально-деловом стиле", callback_data="action_official")],
        [InlineKeyboardButton("Переписать в неформальном стиле", callback_data="action_informal")],
        [InlineKeyboardButton("Обратно в меню", callback_data="action_reset")],
    ]
    await query.edit_message_text(res, reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    # Build application with proxy settings
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request_kwargs({
            "proxy_url": "http://vmhprefy:s7jox1i8odvc@p.webshare.io:80",
            "urllib3_proxy_kwargs": {
                "username": "vmhprefy",
                "password": "s7jox1i8odvc"
            }
        })
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_"))
    app.add_handler(CallbackQueryHandler(action_callback, pattern="^action_"))
    app.run_polling()
