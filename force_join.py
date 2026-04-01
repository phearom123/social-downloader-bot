from urllib.parse import urlparse

def normalize_chat_ref(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("https://t.me/") or value.startswith("http://t.me/"):
        path = urlparse(value).path.strip("/")
        if path.startswith("+"):
            return value  # private invite link, cannot verify membership reliably
        return "@" + path.split("/")[0]
    return value if value.startswith("@") else value

def can_verify(chat_ref: str) -> bool:
    if not chat_ref:
        return False
    return not chat_ref.startswith("http")

def is_joined(bot, chat_ref: str, user_id: int) -> bool:
    if not chat_ref:
        return True
    if not can_verify(chat_ref):
        return False
    try:
        member = bot.get_chat_member(chat_ref, user_id)
        status = getattr(member, "status", "")
        return status in {"creator", "administrator", "member", "restricted"}
    except Exception:
        return False

def check_force_join(bot, user_id: int, mode: str, channel_ref: str, group_ref: str):
    mode = (mode or "both").lower()
    channel_ok = True
    group_ok = True
    if mode in {"channel", "both"}:
        channel_ok = is_joined(bot, channel_ref, user_id)
    if mode in {"group", "both"}:
        group_ok = is_joined(bot, group_ref, user_id)
    if mode == "channel":
        return channel_ok
    if mode == "group":
        return group_ok
    return channel_ok and group_ok
