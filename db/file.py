from db.tool import Db
import json
import time
import mimetypes
import os

class FileDb(Db):
    def __init__(self, path : str, port_api : int):
        super().__init__(path, port_api, -1)

    def create_file_db(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS file (
        sender INTEGER,
        file_name TEXT,
        send_time REAL,
        hash TEXT NOT NULL,
        active BOOLEAN,
        ref_count INTEGER DEFAULT 1,
        last_ref_time REAL
    )
    """
        self.execute(cmd)
        for col, typ in [
            ("ref_count", "INTEGER DEFAULT 1"),
            ("last_ref_time", "REAL"),
            ("size", "INTEGER DEFAULT 0"),
            ("upload_user_count", "INTEGER DEFAULT 1"),
            ("mime_type", "TEXT"),
            ("extension", "TEXT"),
        ]:
            try:
                self.execute("ALTER TABLE file ADD COLUMN {} {}".format(col, typ))
            except Exception:
                pass
        self.execute("UPDATE file SET ref_count = CASE WHEN active THEN 1 ELSE 0 END WHERE ref_count IS NULL")
        self.execute("UPDATE file SET last_ref_time = send_time WHERE last_ref_time IS NULL")
        self.execute("UPDATE file SET size = 0 WHERE size IS NULL")
        self.execute("UPDATE file SET upload_user_count = 1 WHERE upload_user_count IS NULL")
        for hashes, file_name, mime_type, extension in self.query(
                "SELECT hash, file_name, mime_type, extension FROM file"):
            guessed_extension = os.path.splitext(file_name or "")[1].lower()
            guessed_mime = mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"
            if not mime_type or extension is None:
                self.execute(
                    "UPDATE file SET mime_type = ?, extension = ? WHERE hash = ?",
                    (mime_type or guessed_mime,
                     guessed_extension if extension is None else extension,
                     hashes),
                )
        self.create_user_file_table()

    def create_user_file_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS user_file (
        uid INTEGER NOT NULL,
        hash TEXT NOT NULL,
        file_name TEXT,
        upload_time REAL,
        active BOOLEAN DEFAULT TRUE,
        PRIMARY KEY (uid, hash)
    )
    """
        self.execute(cmd)
        for col, typ in [("mime_type", "TEXT"), ("extension", "TEXT")]:
            try:
                self.execute("ALTER TABLE user_file ADD COLUMN {} {}".format(col, typ))
            except Exception:
                pass

    def register_upload(self, uid : int, hashes : str, file_name : str,
                        upload_time : float, size : int = 0,
                        mime_type : str = None, extension : str = None):
        """Atomically register a blob and this user's ownership."""
        with self.lock:
            def operation():
                self.cursor.execute("SELECT 1 FROM file WHERE hash = ?", (hashes,))
                file_exists = self.cursor.fetchone() is not None
                self.cursor.execute(
                    "SELECT active FROM user_file WHERE uid = ? AND hash = ?",
                    (uid, hashes),
                )
                ownership = self.cursor.fetchone()
                already_owned = ownership is not None and bool(ownership[0])

                if not file_exists:
                    self.cursor.execute(
                        """INSERT INTO file
                           (sender, file_name, send_time, hash, active, ref_count,
                            last_ref_time, size, upload_user_count, mime_type, extension)
                           VALUES (?, ?, ?, ?, TRUE, 1, ?, ?, 1, ?, ?)""",
                        (uid, file_name, upload_time, hashes, upload_time, size,
                         mime_type, extension),
                    )
                elif not already_owned:
                    self.cursor.execute(
                        """UPDATE file SET ref_count = ref_count + 1,
                                   upload_user_count = upload_user_count + 1,
                                   last_ref_time = ? WHERE hash = ?""",
                        (upload_time, hashes),
                    )

                self.cursor.execute(
                    """INSERT INTO user_file
                       (uid, hash, file_name, upload_time, active, mime_type, extension)
                       VALUES (?, ?, ?, ?, TRUE, ?, ?)
                       ON CONFLICT(uid, hash) DO UPDATE SET
                           file_name = excluded.file_name,
                           upload_time = excluded.upload_time,
                           active = TRUE,
                           mime_type = excluded.mime_type,
                           extension = excluded.extension""",
                    (uid, hashes, file_name, upload_time, mime_type, extension),
                )
                self.conn.commit()
                return not file_exists, already_owned

            return self._execute_with_retry(operation)

    def acquire_reference(self, uid : int, hashes : str):
        """Acquire a durable content reference while verifying active ownership."""
        with self.lock:
            def operation():
                self.cursor.execute(
                    """SELECT uf.file_name, COALESCE(uf.mime_type, f.mime_type),
                              COALESCE(uf.extension, f.extension), f.size
                       FROM user_file uf JOIN file f ON f.hash = uf.hash
                       WHERE uf.uid = ? AND uf.hash = ? AND uf.active = TRUE""",
                    (uid, hashes),
                )
                row = self.cursor.fetchone()
                if row is None:
                    return None
                self.cursor.execute(
                    "UPDATE file SET ref_count = ref_count + 1, last_ref_time = ? WHERE hash = ?",
                    (time.time(), hashes),
                )
                if self.cursor.rowcount != 1:
                    self.conn.rollback()
                    return None
                self.conn.commit()
                return {
                    "file_name": row[0],
                    "mime_type": row[1] or "application/octet-stream",
                    "extension": row[2] or "",
                    "size": row[3] or 0,
                }

            return self._execute_with_retry(operation)

    def acquire_forward_reference(self, hashes : str):
        """Acquire a forward reference while the initial uploader still owns the blob."""
        with self.lock:
            def operation():
                self.cursor.execute(
                    """SELECT f.file_name, f.mime_type, f.extension, f.size
                       FROM file f JOIN user_file uf
                         ON uf.uid = f.sender AND uf.hash = f.hash
                       WHERE f.hash = ? AND uf.active = TRUE""",
                    (hashes,),
                )
                row = self.cursor.fetchone()
                if row is None:
                    return None
                self.cursor.execute(
                    "UPDATE file SET ref_count = ref_count + 1, last_ref_time = ? WHERE hash = ?",
                    (time.time(), hashes),
                )
                if self.cursor.rowcount != 1:
                    self.conn.rollback()
                    return None
                self.conn.commit()
                return {
                    "file_name": row[0],
                    "mime_type": row[1] or "application/octet-stream",
                    "extension": row[2] or "",
                    "size": row[3] or 0,
                }

            return self._execute_with_retry(operation)

    def tag_file(self, sender : int, file_name : str, send_time : str, hashes : str,
                 size : int = 0, mime_type : str = None, extension : str = None):
        self.execute(
            """INSERT OR IGNORE into file
               (sender, file_name, send_time, hash, active, ref_count, last_ref_time,
                size, upload_user_count, mime_type, extension)
               VALUES (?, ?, ?, ?, TRUE, 1, ?, ?, 1, ?, ?)""",
            (sender, file_name, send_time, hashes, send_time, size, mime_type, extension))

    def add_user_file(self, uid : int, hashes : str, file_name : str, upload_time : float):
        existing = self.query("SELECT * FROM user_file WHERE uid = ? AND hash = ?", (uid, hashes))
        if existing:
            self.execute(
                """UPDATE user_file SET active = TRUE, file_name = ?, upload_time = ?
                   WHERE uid = ? AND hash = ?""",
                (file_name, upload_time, uid, hashes),
            )
        else:
            self.execute(
                "INSERT INTO user_file (uid, hash, file_name, upload_time, active) VALUES (?, ?, ?, ?, TRUE)",
                (uid, hashes, file_name, upload_time))

    def deactivate_user_file(self, uid : int, hashes : str):
        self.execute("UPDATE user_file SET active = FALSE WHERE uid = ? AND hash = ?", (uid, hashes))

    def delete_owned_user_file(self, uid : int, hashes : str):
        with self.lock:
            def operation():
                self.cursor.execute(
                    "SELECT 1 FROM user_file WHERE uid = ? AND hash = ? AND active = TRUE",
                    (uid, hashes),
                )
                if self.cursor.fetchone() is None:
                    return False, []

                self.cursor.execute(
                    "UPDATE user_file SET active = FALSE WHERE uid = ? AND hash = ?",
                    (uid, hashes),
                )
                self.cursor.execute(
                    "UPDATE file SET upload_user_count = MAX(upload_user_count - 1, 0) WHERE hash = ?",
                    (hashes,),
                )
                self.cursor.execute(
                    "UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?",
                    (time.time(), hashes),
                )
                self.cursor.execute(
                    "SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0 AND ref_count <= 0",
                    (hashes,),
                )
                deleted = self.cursor.fetchall()
                if deleted:
                    self.cursor.execute("DELETE FROM file WHERE hash = ?", (hashes,))
                    self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (hashes,))
                self.conn.commit()
                return True, deleted

            return self._execute_with_retry(operation)

    def get_user_files(self, uid : int):
        return self.query(
            "SELECT uf.hash, uf.file_name, uf.upload_time, f.size, f.ref_count, f.upload_user_count, "
            "COALESCE(uf.mime_type, f.mime_type), COALESCE(uf.extension, f.extension) "
            "FROM user_file uf JOIN file f ON uf.hash = f.hash "
            "WHERE uf.uid = ? AND uf.active = TRUE",
            (uid,))

    def get_user_storage_used(self, uid : int):
        result = self.query(
            "SELECT COALESCE(SUM(f.size), 0) FROM user_file uf "
            "JOIN file f ON uf.hash = f.hash "
            "WHERE uf.uid = ? AND uf.active = TRUE",
            (uid,))
        return result[0][0] if result else 0

    def has_active_user_file(self, uid : int, hashes : str):
        result = self.query(
            "SELECT 1 FROM user_file WHERE uid = ? AND hash = ? AND active = TRUE",
            (uid, hashes))
        return bool(result)

    def get_file_size(self, hashes : str):
        result = self.query("SELECT size FROM file WHERE hash = ?", (hashes,))
        return result[0][0] if result else 0

    def increment_ref(self, hashes : str):
        now = time.time()
        self.execute("UPDATE file SET ref_count = ref_count + 1, last_ref_time = ? WHERE hash = ?", (now, hashes))

    def get_metadata(self, hashes : str, owner_uid=None):
        if owner_uid is None:
            rows = self.query(
                """SELECT hash, file_name, size, mime_type, extension, send_time
                   FROM file WHERE hash = ?""",
                (hashes,),
            )
        else:
            rows = self.query(
                """SELECT f.hash, uf.file_name, f.size,
                          COALESCE(uf.mime_type, f.mime_type),
                          COALESCE(uf.extension, f.extension), f.send_time
                   FROM file f
                   LEFT JOIN user_file uf ON uf.hash = f.hash AND uf.uid = ? AND uf.active = TRUE
                   WHERE f.hash = ?""",
                (owner_uid, hashes),
            )
        if not rows:
            return None
        row = rows[0]
        return {
            "hash": row[0],
            "file_name": row[1],
            "filename": row[1],
            "size": row[2] or 0,
            "mime_type": row[3] or "application/octet-stream",
            "extension": row[4] or "",
            "download_url": "/file/get_file/{}".format(row[0]),
            "send_time": row[5],
        }

    def get_active_user_filename(self, uid : int, hashes : str):
        rows = self.query(
            """SELECT file_name FROM user_file
               WHERE uid = ? AND hash = ? AND active = TRUE""",
            (uid, hashes),
        )
        return rows[0][0] if rows else None

    def decrement_ref(self, hashes : str):
        now = time.time()
        self.execute("UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?", (now, hashes))

    def ensure_content_retained(self, hashes : str, reference_count : int = 1):
        self.execute(
            """UPDATE file SET ref_count = MAX(ref_count, upload_user_count + ?),
                       last_ref_time = ? WHERE hash = ?""",
            (max(int(reference_count), 0), time.time(), hashes),
        )

    def reconcile_reference_counts(self, content_references=None):
        """Rebuild counters after upgrades from active ownership and durable content."""
        content_references = content_references or {}
        with self.lock:
            def operation():
                self.cursor.execute("SELECT hash FROM file")
                hashes = [row[0] for row in self.cursor.fetchall()]
                for file_hash in hashes:
                    self.cursor.execute(
                        "SELECT COUNT(*) FROM user_file WHERE hash = ? AND active = TRUE",
                        (file_hash,),
                    )
                    owners = self.cursor.fetchone()[0]
                    total = owners + max(int(content_references.get(file_hash, 0)), 0)
                    self.cursor.execute(
                        """UPDATE file SET upload_user_count = ?, ref_count = ?,
                                   last_ref_time = CASE WHEN ? > 0 THEN ? ELSE last_ref_time END
                           WHERE hash = ?""",
                        (owners, total, total, time.time(), file_hash),
                    )
                self.conn.commit()
                return len(hashes)

            return self._execute_with_retry(operation)

    def decrement_owned_ref(self, uid : int, hashes : str):
        with self.lock:
            def operation():
                self.cursor.execute(
                    "SELECT 1 FROM user_file WHERE uid = ? AND hash = ? AND active = TRUE",
                    (uid, hashes),
                )
                if self.cursor.fetchone() is None:
                    return False
                self.cursor.execute(
                    "UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?",
                    (time.time(), hashes),
                )
                changed = self.cursor.rowcount > 0
                self.conn.commit()
                return changed

            return self._execute_with_retry(operation)

    def increment_upload_user_count(self, hashes : str):
        with self.lock:
            def operation():
                self.cursor.execute("UPDATE file SET upload_user_count = upload_user_count + 1 WHERE hash = ?", (hashes,))
                self.conn.commit()
            return self._execute_with_retry(operation)

    def decrement_upload_user_count(self, hashes : str):
        with self.lock:
            def operation():
                self.cursor.execute("UPDATE file SET upload_user_count = MAX(upload_user_count - 1, 0) WHERE hash = ?", (hashes,))
                self.cursor.execute(
                    "SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0 AND ref_count <= 0",
                    (hashes,),
                )
                result = self.cursor.fetchall()
                if result:
                    self.cursor.execute(
                        "DELETE FROM file WHERE hash = ? AND upload_user_count <= 0 AND ref_count <= 0",
                        (hashes,),
                    )
                    self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (hashes,))
                self.conn.commit()
                return result
            return self._execute_with_retry(operation)

    def file_exists(self, hashes : str):
        result = self.query("SELECT hash FROM file WHERE hash = ?", (hashes,))
        return bool(result)

    def lose_effect(self, file_last_time: float = 72.0):
        time_end = time.time() - file_last_time * 3600
        with self.lock:
            def operation():
                deleted = []
                self.cursor.execute("SELECT * FROM file WHERE upload_user_count <= 0 AND ref_count <= 0")
                orphaned = self.cursor.fetchall()
                for row in orphaned:
                    self.cursor.execute("DELETE FROM file WHERE hash = ?", (row[3],))
                    self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (row[3],))
                    deleted.append(row)
                self.cursor.execute(
                    "SELECT * FROM file WHERE ref_count = 0 AND last_ref_time < ? AND upload_user_count > 0",
                    (time_end,))
                stale = self.cursor.fetchall()
                for row in stale:
                    self.cursor.execute("DELETE FROM file WHERE hash = ?", (row[3],))
                    self.cursor.execute("UPDATE user_file SET active = FALSE WHERE hash = ?", (row[3],))
                    deleted.append(row)
                self.conn.commit()
                return deleted
            return self._execute_with_retry(operation)

    def query_sender_files(self, sender : int):
        return self.query("SELECT * FROM file WHERE sender = ?", (sender,))

    def clean_sender_files(self, sender : int):
        with self.lock:
            def operation():
                now = time.time()
                self.cursor.execute(
                    "SELECT hash FROM user_file WHERE uid = ? AND active = TRUE", (sender,))
                hashes = [row[0] for row in self.cursor.fetchall()]
                self.cursor.execute(
                    "UPDATE user_file SET active = FALSE WHERE uid = ?", (sender,))
                deleted = []
                for h in hashes:
                    self.cursor.execute(
                        "UPDATE file SET upload_user_count = MAX(upload_user_count - 1, 0) WHERE hash = ?", (h,))
                    self.cursor.execute(
                        "UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?",
                        (now, h),
                    )
                    self.cursor.execute(
                        "SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0 AND ref_count <= 0", (h,))
                    orphan = self.cursor.fetchall()
                    if orphan:
                        self.cursor.execute("DELETE FROM file WHERE hash = ?", (h,))
                        self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (h,))
                        deleted.extend(orphan)
                self.conn.commit()
                return deleted

            return self._execute_with_retry(operation)

    def get_all_user_files(self, uid : int = None):
        if uid is not None:
            return self.query(
                "SELECT uf.uid, uf.hash, uf.file_name, uf.upload_time, "
                "f.size, f.ref_count, f.upload_user_count, f.sender, "
                "COALESCE(uf.mime_type, f.mime_type), COALESCE(uf.extension, f.extension) "
                "FROM user_file uf JOIN file f ON uf.hash = f.hash "
                "WHERE uf.active = TRUE AND uf.uid = ?",
                (uid,))
        return self.query(
            "SELECT uf.uid, uf.hash, uf.file_name, uf.upload_time, "
            "f.size, f.ref_count, f.upload_user_count, f.sender, "
            "COALESCE(uf.mime_type, f.mime_type), COALESCE(uf.extension, f.extension) "
            "FROM user_file uf JOIN file f ON uf.hash = f.hash "
            "WHERE uf.active = TRUE")

    def force_delete_file(self, hashes : str):
        with self.lock:
            def operation():
                self.cursor.execute("DELETE FROM file WHERE hash = ?", (hashes,))
                self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (hashes,))
                self.conn.commit()
            return self._execute_with_retry(operation)

    def return_file(self, hashes : str):
        return self.query("SELECT * FROM file WHERE hash = ?", (hashes,))
