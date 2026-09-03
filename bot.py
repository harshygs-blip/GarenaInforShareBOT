"""A minimal Telegram bot that runs as a Render webhook service."""

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply when the user starts a chat with the bot."""
    if update.message:
        await update.message.reply_text("Hello! Main aapka Telegram bot hoon. /help bhejo.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the currently available commands."""
    if update.message:
        await update.message.reply_text("Available commands:\n/start - Bot shuru karo\n/help - Help dekho")


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
