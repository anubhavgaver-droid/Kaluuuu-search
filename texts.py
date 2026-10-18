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
        LINE,
    )


def too_short() -> str:
    return _box("✍️ <b>TOO SHORT</b>", "Please type at least 2 characters.", LINE)


def results(mode: str, hits: list, user_html: str, query: str, elapsed: float) -> str:
    head = {
        "exact": "🔎 <b>SEARCH RESULT</b>",
        "suggest": "🤔 <b>DID YOU MEAN?</b>",
        "tag": "🏷 <b>HASHTAG RESULTS</b>",
    }[mode]
    names = [f"{BULLET} <b>Name:</b> {html.escape(p['title'])}" for p in hits]
    return _box(
        head,
        f"👤 <b>Searched by:</b> {user_html}",
        f"🔍 <b>Query:</b> <i>{html.escape(query[:60])}</i>",
        f"⚡ <b>Found in:</b> {elapsed:.2f} sec",
        LINE,
        *names,
        LINE,
        "👇 <i>Tap a button to get your post</i>",
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
