import re

import database as db

TAG_RE = re.compile(r"#[^\s#.,!?;:()\[\]]+")
# t.me/c/<id>[/<msg>]   or   t.me/<username>[/<msg>]   (message number is optional)
LINK_RE = re.compile(r"(?:https?://)?(?:t|telegram)\.me/(?:c/(\d+)(?:/(\d+))?|([A-Za-z0-9_]{4,})(?:/(\d+))?)")
INVITE_RE = re.compile(r"(?:https?://)?(?:t|telegram)\.me/(?:\+|joinchat/)[\w-]+")
ID_RE = re.compile(r"-?\d{10,14}")
STATUS_TAGS = {"#public", "#private"}


def parse_link(link: str):
    """-> (chat ref, message id or None) or None"""
    link = INVITE_RE.sub(" ", link or "")
    m = LINK_RE.search(link)
    if not m:
        return None
    num, mid_c, uname, mid_u = m.groups()
    ref = int(f"-100{num}") if num else uname
    mid = mid_c or mid_u
    return ref, (int(mid) if mid else None)


def _norm_chat_id(raw: str) -> int:
    digits = raw.lstrip("-")
    if digits.startswith("100") and len(digits) >= 13:
        return -int(digits)
    return int("-100" + digits)


def parse_post(text: str):
    """
    Story Name
    https://t.me/channelname/45      (post number optional; or t.me/c/123/45 for private)
    -1001234567890                   (channel id - needed for private)
    #tag1 #tag2
    #Public  or  #Private
    """
    text = text or ""

    invite_url = None
    inv = INVITE_RE.search(text)
    if inv:
        invite_url = inv.group(0)
        if not invite_url.startswith("http"):
            invite_url = "https://" + invite_url
        text = INVITE_RE.sub(" ", text)

    num = uname = mid = None
    m = LINK_RE.search(text)
    if m:
        num, mid_c, uname, mid_u = m.groups()
        mid = mid_c or mid_u
    rest = LINK_RE.sub(" ", text)

    all_tags = list(dict.fromkeys(TAG_RE.findall(rest)))
    low = {t.lower() for t in all_tags}
    tags = [t for t in all_tags if t.lower() not in STATUS_TAGS]

    if num:
        is_private = True  # t.me/c/... only works for members
    elif uname is None:
        is_private = True  # no public link at all
    else:
        is_private = "#private" in low and "#public" not in low

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
        "target_msg_id": int(mid) if mid else None,
        "invite_url": invite_url,
    }


def post_link(p: dict) -> str:
    mid = p.get("target_msg_id")
    if p["is_private"]:
        num = str(p["target_chat_id"]).replace("-100", "", 1)
        if mid:
            return f"https://t.me/c/{num}/{mid}"
        return p.get("invite_url") or f"https://t.me/c/{num}/1"
    return f"https://t.me/{p['target_username']}/{mid}" if mid else f"https://t.me/{p['target_username']}"


def manual_id(data: dict) -> str:
    ref = data["target_chat_id"] or (data["target_username"] or "").lower()
    return f"m_{ref}_{data['target_msg_id'] or 0}"


def get_text(message) -> str:
    """Visible text/caption plus any hidden hyperlink URLs (e.g. a clickable story name)."""
    from pyrogram.enums import MessageEntityType

    text = str(message.text or message.caption or "")
    ents = message.entities or message.caption_entities or []
    urls = [e.url for e in ents if e.type == MessageEntityType.TEXT_LINK and e.url]
    return text + ("\n" + "\n".join(urls) if urls else "")


def diagnose(text: str) -> str:
    if not text.strip():
        return "no text/caption (media without caption)"
    if parse_post(text) is None:
        return "no t.me link found (or private story without channel ID)"
    return "no story title found"


async def index_message_ex(message):
    """-> (True=new | False=updated | None=skipped, reason)"""
    text = get_text(message)
    if not text.strip():
        return None, diagnose(text)
    data = parse_post(text)
    if not data or not data["title"]:
        return None, diagnose(text)
    new = await db.add_post(db.make_id(message.chat.id, message.id), data)
    return new, "ok"


async def index_message(message):
    return (await index_message_ex(message))[0]
