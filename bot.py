import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["BOT_TOKEN"]
DB_PATH = os.getenv("DATABASE_PATH", "offers.sqlite3")
TTL_HOURS = int(os.getenv("OFFER_TTL_HOURS", "8"))

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nft_url TEXT UNIQUE NOT NULL,
            language TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def valid_nft_url(value):
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "t.me"
        and parsed.path.startswith("/nft/")
        and len(parsed.path.split("/")) == 3
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "NFT Offer Demo — учебный режим.\n"
        "Никакие NFT, подарки или деньги не передаются.\n\n"
        "Команды:\n"
        "/info ссылка язык цена валюта\n"
        "/offer ссылка\n"
        "Пример: /info https://t.me/nft/Demo-1 ru 100 star"
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4:
        await update.message.reply_text(
            "Формат: /info https://t.me/nft/Demo-1 ru 100 star"
        )
        return
    nft_url, language, raw_price, currency = context.args
    try:
        price = float(raw_price)
    except ValueError:
        price = 0
    language = language.lower()
    currency = currency.lower()
    if not valid_nft_url(nft_url) or language not in ("ru", "en") or price <= 0 or currency not in ("star", "gra"):
        await update.message.reply_text("Проверь ссылку, язык (ru/en), положительную цену и валюту (star/gra).")
        return
    conn = db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO listings (nft_url, language, price, currency, owner_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (nft_url, language, price, currency, update.effective_user.id, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()
    await update.message.reply_text(
        "DEMO: объявление сохранено.\n"
        f"NFT-ссылка: {nft_url}\nЦена: {price:g} {currency.upper()}\n"
        "Это только учебная запись — сделки и передача активов не выполняются."
    )

async def offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not valid_nft_url(context.args[0]):
        await update.message.reply_text("Формат: /offer https://t.me/nft/Demo-1")
        return
    conn = db()
    try:
        row = conn.execute(
            "SELECT id, language, price, currency FROM listings WHERE nft_url = ?",
            (context.args[0],)
        ).fetchone()
        if not row:
            await update.message.reply_text("Демо-объявление не найдено. Сначала добавьте его через /info.")
            return
        listing_id, language, price, currency = row
        expires = datetime.now(timezone.utc) + timedelta(hours=TTL_HOURS)
        cur = conn.execute(
            "INSERT INTO offers (listing_id, buyer_id, status, expires_at) VALUES (?, ?, 'pending', ?)",
            (listing_id, update.effective_user.id, expires.isoformat())
        )
        offer_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Принять (DEMO)", callback_data=f"accept:{offer_id}"),
        InlineKeyboardButton("Отклонить", callback_data=f"reject:{offer_id}")
    ]])
    await update.message.reply_text(
        "🧪 ДЕМО-ПРЕДЛОЖЕНИЕ — НЕ НАСТОЯЩАЯ СДЕЛКА\n"
        f"Ссылка: {context.args[0]}\nЦена: {price:g} {currency.upper()}\n"
        f"Срок действия: {TTL_HOURS} ч.\n"
        "Кнопки меняют только статус учебной записи. NFT и деньги не перемещаются.",
        reply_markup=keyboard
    )

async def decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, raw_id = query.data.split(":", 1)
    offer_id = int(raw_id)
    conn = db()
    try:
        row = conn.execute(
            "SELECT status, expires_at FROM offers WHERE id = ?", (offer_id,)
        ).fetchone()
        if not row:
            await query.edit_message_text("Демо-предложение не найдено.")
            return
        status, expires_at = row
        expired = datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
        if expired or status != "pending":
            if status == "pending" and expired:
                conn.execute("UPDATE offers SET status='expired' WHERE id=?", (offer_id,))
                conn.commit()
            await query.edit_message_text("Предложение уже завершено или истекло.")
            return
        new_status = "accepted_demo" if action == "accept" else "rejected_demo"
        conn.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id))
        conn.commit()
    finally:
        conn.close()
    label = "ПРИНЯТО В ДЕМО" if action == "accept" else "ОТКЛОНЕНО"
    await query.edit_message_text(f"🧪 {label}. Никакая реальная сделка не совершалась.")

def main():
    db().close()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("offer", offer))
    app.add_handler(CallbackQueryHandler(decision, pattern=r"^(accept|reject):\d+$"))
    port = int(os.getenv("PORT", "10000"))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TOKEN}",
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
