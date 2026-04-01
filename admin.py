from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from texts import t

def admin_menu(lang):
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton(t(lang, "admin_force_join"), callback_data="admin:forcejoin"),
        InlineKeyboardButton(t(lang, "admin_links"), callback_data="admin:links"),
    )
    m.add(
        InlineKeyboardButton(t(lang, "admin_logs"), callback_data="admin:logs"),
        InlineKeyboardButton(t(lang, "admin_users"), callback_data="admin:users"),
    )
    m.add(
        InlineKeyboardButton(t(lang, "admin_search"), callback_data="admin:search"),
        InlineKeyboardButton(t(lang, "admin_refresh"), callback_data="admin:home"),
    )
    return m

def force_join_menu(lang, enabled: bool, mode: str):
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton(t(lang, "admin_toggle_on") if not enabled else t(lang, "admin_toggle_off"),
                             callback_data="admin:toggle_forcejoin"),
        InlineKeyboardButton(f"{t(lang, 'admin_mode')}: {mode}", callback_data="admin:cycle_mode"),
    )
    m.add(
        InlineKeyboardButton("📢 Channel", callback_data="admin:set_channel"),
        InlineKeyboardButton("👥 Group", callback_data="admin:set_group"),
    )
    m.add(
        InlineKeyboardButton(t(lang, "admin_set_msg"), callback_data="admin:set_join_msg"),
        InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:home"),
    )
    return m
