from db.tool import Db
import time


class MessagesDb(Db):
    def __init__(self, path: str, port_api: int):
        super().__init__(path, port_api, -1)
        self._create_table()
        self._migrate()
        self._create_indexes()

    def _create_table(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                mid INTEGER PRIMARY KEY AUTOINCREMENT,
                client_mid TEXT,
                sender_uid INTEGER NOT NULL,
                receiver_uid INTEGER NOT NULL,
                group_id INTEGER,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'plain',
                file_hash TEXT,
                send_time REAL NOT NULL,
                quote INTEGER NOT NULL DEFAULT -1,
                deleted INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS room_preferences (
                uid INTEGER NOT NULL,
                room_id TEXT NOT NULL,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                notify_level INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY (uid, room_id)
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS message_mentions (
                mid INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                PRIMARY KEY (mid, uid)
            )
        """)

    def _migrate(self):
        """尝试修复db"""
        from sqlite3 import OperationalError
        for col, typ in [("group_id", "INTEGER"), ("client_mid", "TEXT")]:
            try:
                self.execute("ALTER TABLE messages ADD COLUMN {} {}".format(col, typ))
            except OperationalError:
                pass

    def _create_indexes(self):
        from sqlite3 import OperationalError
        try:
            self.execute("DROP INDEX IF EXISTS idx_messages_client_mid")
        except Exception:
            pass
        indexes = [
            """CREATE INDEX IF NOT EXISTS idx_messages_conversation
               ON messages(sender_uid, receiver_uid, send_time DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_messages_receiver
               ON messages(receiver_uid, send_time DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_messages_group
               ON messages(group_id, send_time DESC)""",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_sender_client_mid
               ON messages(sender_uid, client_mid) WHERE client_mid IS NOT NULL""",
        ]
        for idx_sql in indexes:
            try:
                self.execute(idx_sql)
            except OperationalError:
                pass

    def add_message(self, sender_uid: int, receiver_uid: int, content: str,
                    content_type: str = 'plain', file_hash: str = None,
                    quote: int = -1, group_id: int = None,
                    client_mid: str = None) -> dict:
        send_time = time.time()
        from sqlite3 import IntegrityError
        with self.lock:
            def operation():
                try:
                    self.cursor.execute(
                        """INSERT INTO messages
                           (client_mid, sender_uid, receiver_uid, group_id, content, content_type,
                            file_hash, send_time, quote)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (client_mid, sender_uid, receiver_uid, group_id, content, content_type,
                         file_hash, send_time, quote),
                    )
                    mid = self.cursor.lastrowid
                    self.conn.commit()
                    return mid, False
                except IntegrityError:
                    self.conn.rollback()
                    if client_mid:
                        self.cursor.execute(
                            "SELECT mid FROM messages WHERE sender_uid = ? AND client_mid = ?",
                            (sender_uid, client_mid),
                        )
                        existing = self.cursor.fetchone()
                        if existing:
                            return existing[0], True
                    raise

            mid, duplicate = self._execute_with_retry(operation)

        if duplicate:
            return {"mid": mid, "duplicate": True}
        return {
            "mid": mid,
            "client_mid": client_mid,
            "sender_uid": sender_uid,
            "receiver_uid": receiver_uid,
            "group_id": group_id,
            "content": content,
            "content_type": content_type,
            "file_hash": file_hash,
            "send_time": send_time,
            "quote": quote,
            "deleted": 0,
        }

    def query_history(self, uid: int, target_uid: int,
                      before_mid: int = 0, limit: int = 50,
                      group_id: int = None) -> list:
        """返回历史消息，按 mid 倒序排列。"""
        if group_id is not None:
            where = "deleted = 0 AND group_id = ?"
            params = [group_id]
        else:
            where = ("deleted = 0 AND group_id IS NULL AND "
                     "((sender_uid = ? AND receiver_uid = ?) "
                     "OR (sender_uid = ? AND receiver_uid = ?))")
            params = [uid, target_uid, target_uid, uid]

        if before_mid > 0:
            where += " AND mid < ?"
            params.append(before_mid)

        sql = """SELECT mid, client_mid, sender_uid, receiver_uid, group_id,
                        content, content_type, file_hash, send_time, quote, deleted
                 FROM messages WHERE {} ORDER BY mid DESC LIMIT ?""".format(where)
        params.append(limit)
        return self.query(sql, tuple(params))

    _COLUMNS = ["mid", "client_mid", "sender_uid", "receiver_uid", "group_id",
                "content", "content_type", "file_hash", "send_time", "quote", "deleted"]

    def serialize_rows(self, rows) -> list:
        records = [dict(zip(self._COLUMNS, r)) for r in rows]
        if not records:
            return records
        mids = [record["mid"] for record in records]
        placeholders = ",".join("?" * len(mids))
        mention_rows = self.query(
            "SELECT mid, uid FROM message_mentions WHERE mid IN ({})".format(placeholders),
            tuple(mids),
        )
        mentions = {}
        for mid, uid in mention_rows:
            mentions.setdefault(mid, []).append(uid)
        for record in records:
            record["mentioned_uids"] = mentions.get(record["mid"], [])
        return records

    def get_chat_list(self, uid: int) -> list:
        """返回与每个用户的最新单聊消息。
        群聊由 API 接口单独合并。
        """
        rows = self.query(
            """SELECT partner_uid, mid, client_mid, sender_uid, content, content_type, send_time
               FROM (
                 SELECT
                   CASE WHEN sender_uid = ? THEN receiver_uid ELSE sender_uid END AS partner_uid,
                   mid, client_mid, sender_uid, content, content_type, send_time,
                   ROW_NUMBER() OVER (
                     PARTITION BY CASE WHEN sender_uid = ? THEN receiver_uid ELSE sender_uid END
                     ORDER BY mid DESC
                   ) AS rn
                 FROM messages
                 WHERE deleted = 0 AND group_id IS NULL
                   AND (sender_uid = ? OR receiver_uid = ?)
                   AND sender_uid != receiver_uid
               )
               WHERE rn = 1 AND partner_uid != ?
               ORDER BY mid DESC""",
            (uid, uid, uid, uid, uid)
        )
        return [
            {
                "partner_uid": r[0],
                "group_id": None,
                "last_mid": r[1],
                "last_client_mid": r[2],
                "last_sender_uid": r[3],
                "last_content": r[4],
                "last_content_type": r[5],
                "last_time": r[6],
            }
            for r in rows
        ]

    def get_group_last_message(self, group_id: int) -> dict:
        """返回群聊的最新消息，如果没有则返回 None。"""
        rows = self.query(
            """SELECT mid, sender_uid, content, content_type, send_time
               FROM messages
               WHERE deleted = 0 AND group_id = ?
               ORDER BY mid DESC LIMIT 1""",
            (group_id,)
        )
        if not rows:
            return None
        return {
            "mid": rows[0][0],
            "sender_uid": rows[0][1],
            "content": rows[0][2],
            "content_type": rows[0][3],
            "send_time": rows[0][4],
        }

    def get_group_last_messages(self, group_ids: list) -> dict:
        """批量获取多个群聊的最新消息，单次查询。"""
        if not group_ids:
            return {}
        placeholders = ",".join("?" * len(group_ids))
        rows = self.query(
            """SELECT m.mid, m.sender_uid, m.content, m.content_type, m.send_time, m.group_id
               FROM messages m
               INNER JOIN (
                   SELECT group_id, MAX(mid) AS max_mid
                   FROM messages
                   WHERE deleted = 0 AND group_id IN ({})
                   GROUP BY group_id
               ) latest ON m.group_id = latest.group_id AND m.mid = latest.max_mid
            """.format(placeholders),
            tuple(group_ids)
        )
        return {
            r[5]: {
                "mid": r[0], "sender_uid": r[1], "content": r[2],
                "content_type": r[3], "send_time": r[4],
            }
            for r in rows
        }

    def verify_quote(self, quote_mid: int, sender_uid: int = 0,
                     target_uid: int = 0, group_id: int = None) -> bool:
        rows = self.query(
            "SELECT sender_uid, receiver_uid, group_id, deleted FROM messages WHERE mid = ?",
            (quote_mid,)
        )
        if not rows:
            return False
        r = rows[0]
        if r[3]:  # deleted
            return False
        if group_id is not None:
            return r[2] == group_id
        return (r[0] == sender_uid and r[1] == target_uid) or \
               (r[0] == target_uid and r[1] == sender_uid)

    def delete_message(self, mid: int) -> bool:
        self.execute("UPDATE messages SET deleted = 1 WHERE mid = ?", (mid,))
        return True

    def get_room_preferences(self, uid: int) -> dict:
        rows = self.query(
            "SELECT room_id, is_pinned, notify_level FROM room_preferences WHERE uid = ?",
            (uid,),
        )
        return {
            row[0]: {"is_pinned": bool(row[1]), "notify_level": int(row[2])}
            for row in rows
        }

    def get_room_preference(self, uid: int, room_id: str) -> dict:
        rows = self.query(
            "SELECT is_pinned, notify_level FROM room_preferences WHERE uid = ? AND room_id = ?",
            (uid, room_id),
        )
        if not rows:
            return {"is_pinned": False, "notify_level": 0}
        return {"is_pinned": bool(rows[0][0]), "notify_level": int(rows[0][1])}

    def update_room_preference(self, uid: int, room_id: str,
                               is_pinned=None, notify_level=None) -> bool:
        current = self.query(
            "SELECT is_pinned, notify_level FROM room_preferences WHERE uid = ? AND room_id = ?",
            (uid, room_id),
        )
        pinned = int(bool(is_pinned)) if is_pinned is not None else (
            int(current[0][0]) if current else 0
        )
        level = int(notify_level) if notify_level is not None else (
            int(current[0][1]) if current else 0
        )
        if level not in (0, 1, 2):
            return False
        self.execute(
            """INSERT INTO room_preferences(uid, room_id, is_pinned, notify_level, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(uid, room_id) DO UPDATE SET
                 is_pinned = excluded.is_pinned,
                 notify_level = excluded.notify_level,
                 updated_at = excluded.updated_at""",
            (uid, room_id, pinned, level, time.time()),
        )
        return True

    def set_message_mentions(self, mid: int, mentioned_uids) -> None:
        values = [(mid, int(uid)) for uid in set(mentioned_uids)]
        if values:
            self.update(
                "INSERT OR IGNORE INTO message_mentions(mid, uid) VALUES (?, ?)",
                values,
            )
