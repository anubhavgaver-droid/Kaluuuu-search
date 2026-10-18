"""All user-facing message designs live here - edit freely to restyle the bot."""
import html

LINE = "━━━━━━━━━━━━━━━━━━"
BULLET = "◉"


def _box(head: str, *lines: str) -> str:
    return "\n".join([LINE, head, LINE, *lines])


def mention(user) -> str:
    name = html.escape((user.first_name or "User")[:30])
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def welcome() -> str:
    return _box(
        "👋 <b>WELCOME TO STORY SEARCH</b>",
        f"{BULLET} Send a story name to search",
        f"{BULLET} Spelling mistakes are fine",
        f"{BULLET} Try hashtags like <code>#romance</code>",
        f"{BULLET} Works in groups too",
        f"{BULLET} /filters - see all stories (tap a name to copy)",
        f"{BULLET} /request <i>name</i> - request a new story",
        LINE,
    )


def too_short() -> str:
    return _box("✍️ <b>TOO SHORT</b>", "Please type at least 2 characters.", LINE)


_AI_FRAMES = [
    ("🔍", "▰▱▱▱▱▱▱▱", "Scanning the story library…"),
    ("🔎", "▰▰▰▱▱▱▱▱", "Understanding your spelling…"),
    ("🔍", "▰▰▰▰▰▱▱▱", "Matching similar names…"),
    ("✨", "▰▰▰▰▰▰▰▰", "Picking the best results…"),
]
AI_FRAME_COUNT = len(_AI_FRAMES)


def ai_frame(i: int) -> str:
    icon, bar, status = _AI_FRAMES[min(i, AI_FRAME_COUNT - 1)]
    return _box(
        f"🤖 <b>AI SEARCH</b> {icon}",
        f"<code>{bar}</code>",
        f"⚡ <i>{status}</i>",
        LINE,
    )


def results(mode: str, hits: list, user_html: str, query: str, elapsed: float, page_info=None) -> str:
    head = {
        "exact": "🔎 <b>SEARCH RESULT</b>",
        "suggest": "🤔 <b>DID YOU MEAN?</b>",
        "tag": "🏷 <b>HASHTAG RESULTS</b>",
    }[mode]
    if mode == "suggest":
        names = [f"{BULLET} <b>Name:</b> {html.escape(p['title'])}" for p in hits]
        foot = "🤖 <i>AI picked the best matches - tap one to get it</i>"
    else:
        names = [f"{BULLET} <b>Name:</b> {html.escape(p['title'])}" for p in hits]
        foot = "👇 <i>Tap a button to get your post</i>"
    info = [f"📄 <b>Page:</b> {page_info[0]}/{page_info[1]}  •  <b>Total:</b> {page_info[2]}"] if page_info else []
    return _box(
        head,
        f"👤 <b>Searched by:</b> {user_html}",
        f"🔍 <b>Query:</b> <i>{html.escape(query[:60])}</i>",
        f"⚡ <b>Found in:</b> {elapsed:.2f} sec",
        *info,
        LINE,
        *names,
        LINE,
        foot,
    )


def not_found(user_html: str, query: str, elapsed: float) -> str:
    return _box(
        "❌ <b>NOTHING FOUND</b>",
        f"👤 <b>Searched by:</b> {user_html}",
        f"🔍 <b>Query:</b> <i>{html.escape(query[:60])}</i>",
        f"⚡ <b>Checked in:</b> {elapsed:.2f} sec",
        LINE,
        "Check the spelling or try another name.",
    )


def link_ready(title: str) -> str:
    return _box(
        "✅ <b>YOUR POST IS READY</b>",
        f"{BULLET} <b>Name:</b> {html.escape(title)}",
        LINE,
        "👇 <i>Tap below to open it</i>",
    )


def join_required(title: str) -> str:
    return _box(
        "🔒 <b>JOIN REQUIRED</b>",
        f"{BULLET} <b>Name:</b> {html.escape(title)}",
        LINE,
        "First join this channel, because the post is uploaded there.",
        "Then tap <b>✅ I've joined</b> to get your link.",
    )


def removed() -> str:
    return _box("⚠️ <b>POST REMOVED</b>", "This post is no longer available.")


def cant_check() -> str:
    return _box("⚠️ <b>CAN'T CHECK CHANNEL</b>", "Please tell the admin (the bot must be admin there).")


def cant_invite() -> str:
    return _box("⚠️ <b>JOIN LINK FAILED</b>", "Couldn't create a join link. Please contact the admin.")


# ---------- story library (/filters) ----------
def library(chunk: list, page: int, pages: int, total_all: int, matched: int, arg: str) -> str:
    info = [f"📦 <b>Total stories:</b> {total_all}"]
    if arg:
        info.append(f"🔎 <b>Filter:</b> <i>{html.escape(arg[:40])}</i>  •  <b>Matched:</b> {matched}")
    info.append(f"📄 <b>Page:</b> {page + 1}/{pages}")
    names = [f"{BULLET} <code>{html.escape(t)}</code>" for t in chunk]
    return _box(
        "📚 <b>STORY LIBRARY</b>",
        *info,
        LINE,
        *names,
        LINE,
        "👆 <i>Tap a name to copy it, then send it to me to search</i>",
    )


def library_empty(arg: str) -> str:
    return _box("📚 <b>STORY LIBRARY</b>", f"Nothing matched <i>{html.escape(arg[:40])}</i>." if arg else "No stories yet.")


# ---------- story requests ----------
def request_usage() -> str:
    return _box("📨 <b>REQUEST A STORY</b>", "Send the story name like this:", "<code>/request Story Name</code>")


def request_exists(user_html: str, name: str, hits: list) -> str:
    names = [f"{BULLET} <b>Name:</b> {html.escape(p['title'])}" for p in hits]
    return _box(
        "✅ <b>ALREADY AVAILABLE</b>",
        f"👤 <b>Requested by:</b> {user_html}",
        f"🔍 <b>Request:</b> <i>{html.escape(name[:60])}</i>",
        LINE,
        *names,
        LINE,
        "👇 <i>No need to request - tap to get it</i>",
    )


def request_sent(name: str) -> str:
    return _box(
        "📨 <b>REQUEST SENT</b>",
        f"{BULLET} <b>Story:</b> {html.escape(name[:80])}",
        LINE,
        "✅ The admin has been notified.",
        "You'll get a message here when it's added.",
    )


def request_limit(n: int) -> str:
    return _box("⏳ <b>REQUEST LIMIT</b>", f"You can send {n} requests per day. Please try again later.")


def request_admin(name: str, user_html: str, uid: int, where: str) -> str:
    return _box(
        "📨 <b>NEW STORY REQUEST</b>",
        f"{BULLET} <b>Story:</b> {html.escape(name[:100])}",
        f"👤 <b>From:</b> {user_html}  <code>{uid}</code>",
        f"📍 <b>Where:</b> {html.escape(where[:50])}",
    )


def request_done(name: str, ok: bool) -> str:
    if ok:
        return _box("✅ <b>STORY ADDED</b>", f"{BULLET} <b>Story:</b> {html.escape(name[:80])}", LINE, "Search it now - it's available! 🎉")
    return _box("❌ <b>REQUEST DECLINED</b>", f"{BULLET} <b>Story:</b> {html.escape(name[:80])}", LINE, "Sorry, this story couldn't be added right now.")


def request_list(rows: list, total: int) -> str:
    lines = [f"{BULLET} <code>{html.escape(r['query'][:60])}</code> - {html.escape(r.get('user_name', '?')[:20])}" for r in rows]
    return _box("📨 <b>PENDING REQUESTS</b>", f"📦 <b>Total pending:</b> {total}", LINE, *(lines or ["Nothing pending 🎉"]))


def not_your_search() -> str:
    return _box(
        "🙅 <b>NOT YOUR SEARCH</b>",
        "This result was searched by someone else.",
        "Please search your own story 🔍",
        LINE,
        "👇 <i>Go to the group and search yours</i>",
    )
