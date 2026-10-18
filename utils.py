import re

import database as db

TAG_RE = re.compile(r"#[^\s#.,!?;:()\[\]]+")
LINK_RE = re.compile(r"(?:https?://)?t\.me/(?:c/(\d+)|([A-Za-z0-9_]{4,}))/(\d+)")
ID_RE = re.compile(r"-?\d{10,14}")
STATUS_TAGS = {"#public", "#private"}


def parse_link(link: str):
    m = LINK_RE.search(link or "")
    if not m:
        return None
    num, uname, mid = m.groups()
    ref = int(f"-100{num}") if num else uname
    return ref, int(mid)


def _norm_chat_id(raw: str) -> int:
    digits = raw.lstrip("-")
    if digits.startswith("100") and len(digits) >= 13:
        return -int(digits)
    return int("-100" + digits)


def parse_post(text: str):
    """
    Parse a post written in this format:

        Story Name
        https://t.me/c/1234567890/45      (or https://t.me/channelname/45)
        -1001234567890                    (channel id, for private)
        #tag1 #tag2
        #Private                          (or #Public)

    Returns a dict or None if the post has no usable link.
    """
    m = LINK_RE.search(text or "")
    if not m:
        return None
    num, uname, mid = m.groups()
    rest = LINK_RE.sub(" ", text)

    all_tags = list(dict.fromkeys(TAG_RE.findall(rest)))
    low = {t.lower() for t in all_tags}
    tags = [t for t in all_tags if t.lower() not in STATUS_TAGS]

    # a t.me/c/... link only works for members, so it is always private
    is_private = bool(num) or ("#private" in low and "#public" not in low)

    chat_id = int(f"-100{num}") if num else None
    if is_private and chat_id is None:
        idm = ID_RE.search(TAG_RE.sub(" ", rest))
        if idm:
            chat_id = _norm_chat_id(idm.group())
    if is_private and chat_id is None:
        return None  # private but no channel id -> can't verify membership

    title = ""
    for line in rest.splitlines():
        line = ID_RE.sub("", TAG_RE.sub("", line)).strip()
        line = re.sub(r"^[\s\W_]+", "", line)
        if line:
            title = line
            break

    return {
        "title": title[:100],
        "hashtags": tags,
        "is_private": is_private,
        "target_chat_id": chat_id,
        "target_username": None if is_private else uname,
        "target_msg_id": int(mid),
    }


def post_link(p: dict) -> str:
    if p["is_private"]:
        return f"https://t.me/c/{str(p['target_chat_id']).replace('-100', '', 1)}/{p['target_msg_id']}"
    return f"https://t.me/{p['target_username']}/{p['target_msg_id']}"


def manual_id(data: dict) -> str:
    ref = data["target_chat_id"] or (data["target_username"] or "").lower()
    return f"m_{ref}_{data['target_msg_id']}"


async def index_message(message):
    """Index one post of the index channel. True=new, False=updated, None=skipped."""
    text = message.text or message.caption
    if not text:
        return None
    data = parse_post(text)
    if not data or not data["title"]:
        return None
    return await db.add_post(db.make_id(message.chat.id, message.id), data)
