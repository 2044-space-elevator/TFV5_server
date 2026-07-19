from db.tool import Db
import json
import time

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
        ]:
            try:
                self.execute("ALTER TABLE file ADD COLUMN {} {}".format(col, typ))
            except Exception:
                pass
        self.execute("UPDATE file SET ref_count = CASE WHEN active THEN 1 ELSE 0 END WHERE ref_count IS NULL")
        self.execute("UPDATE file SET last_ref_time = send_time WHERE last_ref_time IS NULL")
        self.execute("UPDATE file SET size = 0 WHERE size IS NULL")
        self.execute("UPDATE file SET upload_user_count = 1 WHERE upload_user_count IS NULL")
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

    def tag_file(self, sender : int, file_name : str, send_time : str, hashes : str, size : int = 0):
        self.execute(
            "INSERT into file (sender, file_name, send_time, hash, active, ref_count, last_ref_time, size, upload_user_count) VALUES (?, ?, ?, ?, TRUE, 1, ?, ?, 1)",
            (sender, file_name, send_time, hashes, send_time, size))

    def add_user_file(self, uid : int, hashes : str, file_name : str, upload_time : float):
        existing = self.query("SELECT * FROM user_file WHERE uid = ? AND hash = ?", (uid, hashes))
        if existing:
            self.execute("UPDATE user_file SET active = TRUE, upload_time = ? WHERE uid = ? AND hash = ?",
                         (upload_time, uid, hashes))
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
                    "SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0",
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
            "SELECT uf.hash, uf.file_name, uf.upload_time, f.size, f.ref_count, f.upload_user_count "
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

    def decrement_ref(self, hashes : str):
        now = time.time()
        self.execute("UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?", (now, hashes))

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
                self.cursor.execute("SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0", (hashes,))
                result = self.cursor.fetchall()
                if result:
                    self.cursor.execute("DELETE FROM file WHERE hash = ? AND upload_user_count <= 0", (hashes,))
                    self.cursor.execute("DELETE FROM user_file WHERE hash = ?", (hashes,))
                self.conn.commit()
                return result
            return self._execute_with_retry(operation)

    def file_exists(self, hashes : str):
        result = self.query("SELECT hash FROM file WHERE hash = ?", (hashes,))
        return bool(result)

    def lose_effect(self):
        time_end = time.time()
        with open("res/{}/config.json".format(self.api_pt), "r+") as file:
            time_end -= json.load(file)["file_last_time"] * 3600
        with self.lock:
            def operation():
                deleted = []
                self.cursor.execute("SELECT * FROM file WHERE upload_user_count <= 0")
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
                    "UPDATE user_file SET active = FALSE WHERE uid = ?", (sender,))
                deleted = []
                self.cursor.execute(
                    "SELECT hash FROM user_file WHERE uid = ?", (sender,))
                hashes = [row[0] for row in self.cursor.fetchall()]
                for h in hashes:
                    self.cursor.execute(
                        "UPDATE file SET upload_user_count = MAX(upload_user_count - 1, 0) WHERE hash = ?", (h,))
                    self.cursor.execute(
                        "SELECT * FROM file WHERE hash = ? AND upload_user_count <= 0", (h,))
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
                "f.size, f.ref_count, f.upload_user_count, f.sender "
                "FROM user_file uf JOIN file f ON uf.hash = f.hash "
                "WHERE uf.active = TRUE AND uf.uid = ?",
                (uid,))
        return self.query(
            "SELECT uf.uid, uf.hash, uf.file_name, uf.upload_time, "
            "f.size, f.ref_count, f.upload_user_count, f.sender "
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
