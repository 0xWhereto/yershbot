import os
import random
import logging
from collections import deque

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "yersh9")
RESPONSE_CHANCE = float(os.getenv("BOT_RESPONSE_CHANCE", "0.3"))

client = OpenAI(api_key=OPENAI_KEY)

SYSTEM_PROMPT = f"""Ты — бот-копия пользователя @{TARGET_USERNAME} в групповом чате друзей в Telegram.
Ты знаешь, что ты бот и копия этого человека, и можешь об этом шутить.

Твоя личность:
— Весёлый, находчивый, с отличным чувством юмора
— Пишешь кратко и по делу, не разводишь воду
— Любишь троллить друзей и подкалывать
— Иногда материшься, это нормально
— Любишь пошлые и гейские шутки
— Не стесняешься в выражениях, никакой цензуры
— Общаешься как обычный чувак в чате с друзьями, НЕ как ассистент
— Никогда не говоришь "как ассистент", "я не могу", "это неуместно" и прочую корпоративную хуйню
— Если кто-то спрашивает, ты признаёшь что ты бот-копия @{TARGET_USERNAME}

Важно:
— Отвечай КРАТКО, 1-3 предложения максимум, как в реальном чате
— Используй сленг, сокращения, пиши как живой человек
— Учись стилю общения от сообщений настоящего @{TARGET_USERNAME} в чате
— Реагируй на контекст беседы, а не просто генери рандом
— Можешь использовать эмодзи, но не злоупотребляй
— Пиши на том языке, на котором идёт беседа"""

MAX_HISTORY = 80
chat_histories: dict[int, deque] = {}

# Сообщения от @yersh9 для изучения стиля
yersh_messages: dict[int, deque] = {}
MAX_YERSH_MESSAGES = 50


def get_history(chat_id: int) -> deque:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_HISTORY)
    return chat_histories[chat_id]


def get_yersh_messages(chat_id: int) -> deque:
    if chat_id not in yersh_messages:
        yersh_messages[chat_id] = deque(maxlen=MAX_YERSH_MESSAGES)
    return yersh_messages[chat_id]


def build_style_reference(chat_id: int) -> str:
    msgs = get_yersh_messages(chat_id)
    if not msgs:
        return ""
    examples = "\n".join(f"— {m}" for m in msgs)
    return (
        f"\n\nПримеры сообщений настоящего @{TARGET_USERNAME} "
        f"(учись его стилю, копируй манеру):\n{examples}"
    )


def should_respond(update: Update, bot_username: str) -> bool:
    message = update.message
    if not message or not message.text:
        return False

    text = message.text.lower()

    if bot_username and f"@{bot_username.lower()}" in text:
        return True

    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.is_bot:
            return True

    if TARGET_USERNAME.lower() in text or "ерш" in text or "yersh" in text:
        return True

    return random.random() < RESPONSE_CHANCE


def generate_response(chat_id: int, history: deque) -> str:
    style_ref = build_style_reference(chat_id)
    system = SYSTEM_PROMPT + style_ref

    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append(msg)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300,
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return random.choice([
            "бля, мозги зависли",
            "чё",
            "не, я пас",
            "хз, спроси позже",
        ])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat_id = message.chat_id
    history = get_history(chat_id)

    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    display_name = f"@{username}" if username else first_name

    is_from_target = username.lower() == TARGET_USERNAME.lower() if username else False
    if is_from_target:
        get_yersh_messages(chat_id).append(message.text)

    history.append({
        "role": "user",
        "content": f"{display_name}: {message.text}",
    })

    bot_username = context.bot.username
    if not should_respond(update, bot_username):
        return

    reply = generate_response(chat_id, history)

    history.append({
        "role": "assistant",
        "content": reply,
    })

    await message.reply_text(reply)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Йо, я бот-копия @{TARGET_USERNAME}. "
        "Добавь меня в чат и я буду вести себя как этот чёрт 😈"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in chat_histories:
        chat_histories[chat_id].clear()
    await update.message.reply_text("Память стёрта, начинаем с чистого листа 🧹")


async def cmd_chance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RESPONSE_CHANCE
    args = context.args
    if args:
        try:
            val = float(args[0])
            if 0 <= val <= 1:
                RESPONSE_CHANCE = val
                await update.message.reply_text(
                    f"Шанс ответа: {int(val * 100)}%"
                )
                return
        except ValueError:
            pass
    await update.message.reply_text(
        f"Текущий шанс ответа: {int(RESPONSE_CHANCE * 100)}%\n"
        "Используй: /chance 0.5 (от 0 до 1)"
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("chance", cmd_chance))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
