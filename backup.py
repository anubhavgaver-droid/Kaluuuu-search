import gzip
import io
from datetime import datetime

from bson import json_util

import database as db
import texts
from config import Config


def target_chat():
    return Config.BACKUP_CHAT_ID or (Config.ADMINS[0] if Config.ADMINS else None)


async def send_backup(client, chat_id):
    data = await db.export_all()
    buf = io.BytesIO(gzip.compress(json_util.dumps(data).encode()))
    name = f"backup_{datetime.utcnow():%Y-%m-%d_%H%M}.json.gz"
    buf.name = name
    counts = {k: len(v) for k, v in data.items()}
    await client.send_document(chat_id, buf, file_name=name, caption=texts.backup_caption(counts))
    return counts


async def restore_backup(raw: bytes) -> dict:
    data = json_util.loads(gzip.decompress(raw).decode())
    return await db.import_all(data)
