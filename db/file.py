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
        for col, typ in [("ref_count", "INTEGER DEFAULT 1"), ("last_ref_time", "REAL")]:
            try:
                self.execute("ALTER TABLE file ADD COLUMN {} {}".format(col, typ))
            except Exception:
                pass
        self.execute("UPDATE file SET ref_count = CASE WHEN active THEN 1 ELSE 0 END WHERE ref_count IS NULL")
        self.execute("UPDATE file SET last_ref_time = send_time WHERE last_ref_time IS NULL")

    def tag_file(self, sender : int, file_name : str, send_time : str, hashes : str):
        self.execute(
            "INSERT into file (sender, file_name, send_time, hash, active, ref_count, last_ref_time) VALUES (?, ?, ?, ?, TRUE, 1, ?)",
            (sender, file_name, send_time, hashes, send_time))

    def increment_ref(self, hashes : str):
        now = time.time()
        self.execute("UPDATE file SET ref_count = ref_count + 1, last_ref_time = ? WHERE hash = ?", (now, hashes))

    def decrement_ref(self, hashes : str):
        now = time.time()
        self.execute("UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE hash = ?", (now, hashes))

    def lose_effect(self):
        time_end = time.time()
        with open("res/{}/config.json".format(self.api_pt), "r+") as file:
            time_end -= json.load(file)["file_last_time"] * 3600
        query_ans = self.query("SELECT * FROM file WHERE ref_count = 0 AND last_ref_time < ?", (time_end,))
        self.execute("DELETE FROM file WHERE ref_count = 0 AND last_ref_time < ?", (time_end,))
        return query_ans

    def query_sender_files(self, sender : int):
        return self.query("SELECT * FROM file WHERE sender = ?", (sender,))

    def clean_sender_files(self, sender : int):
        with self.lock:
            def operation():
                now = time.time()
                self.cursor.execute(
                    "UPDATE file SET ref_count = MAX(ref_count - 1, 0), last_ref_time = ? WHERE sender = ?",
                    (now, sender))
                self.cursor.execute("SELECT * FROM file WHERE sender = ? AND ref_count = 0", (sender,))
                deleted = self.cursor.fetchall()
                self.cursor.execute("DELETE FROM file WHERE sender = ? AND ref_count = 0", (sender,))
                self.conn.commit()
                return deleted

            return self._execute_with_retry(operation)

    def return_file(self, hashes : str):
        return self.query("SELECT * FROM file WHERE hash = ?", (hashes,))