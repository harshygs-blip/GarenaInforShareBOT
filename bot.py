"""A minimal Telegram bot that runs as a Render webhook service."""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply when the user starts a chat with the bot."""
    if update.message:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Help", callback_data="help")],
                [InlineKeyboardButton("About", callback_data="about")],
            ]
        )
        await update.message.reply_text(
            "Hello! Main GarenShareinfo bot hoon. Neeche option select karo.",
            reply_markup=keyboard,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the currently available commands."""
    if update.message:
        await update.message.reply_text("Available commands:\n/start - Bot shuru karo\n/help - Help dekho")


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Describe the bot's currently available purpose."""
    if update.message:
        await update.message.reply_text("GarenShareinfo ek simple information and support bot hai.")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm that the bot is running."""
    if update.message:
        await update.message.reply_text("Bot online hai.")


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the safe information buttons shown by /start."""
    query = update.callback_query
    if not query:
        return

    await query.answer()
    responses = {
        "help": "Commands:\n/start - Main menu\n/help - Help\n/about - Bot ke baare mein\n/ping - Bot status",
        "about": "GarenShareinfo ek simple information and support bot hai.",
    }
    await query.message.reply_text(responses.get(query.data, "Option available nahi hai."))


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    base_url = os.environ.get("WEBHOOK_BASE_URL")
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    if not base_url or not webhook_secret:
        raise RuntimeError("WEBHOOK_BASE_URL and WEBHOOK_SECRET must be set.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CallbackQueryHandler(button_click))

    port = int(os.environ.get("PORT", "8000"))
    webhook_url = f"{base_url.rstrip('/')}/{webhook_secret}"
    print("Bot webhook service chal rahi hai.")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_secret,
        webhook_url=webhook_url,
    )


if __name__ == "__main__":
    main()
