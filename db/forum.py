from db.tool import Db
from time import time
import json
import threading


_comments_locks = {}
_comments_locks_lock = threading.Lock()


def comments_path(port_api : int):
    return "res/{}/forum/comments.json".format(port_api)


def get_comments_lock(port_api : int):
    with _comments_locks_lock:
        lock = _comments_locks.get(port_api)
        if lock is None:
            lock = threading.Lock()
            _comments_locks[port_api] = lock
        return lock


def read_comments(port_api : int):
    with get_comments_lock(port_api):
        with open(comments_path(port_api), "r", encoding="utf-8") as file:
            return json.load(file)


def update_comments(port_api : int, callback):
    with get_comments_lock(port_api):
        with open(comments_path(port_api), "r+", encoding="utf-8") as file:
            comments = json.load(file)
        result = callback(comments)
        with open(comments_path(port_api), "w+", encoding="utf-8") as file:
            json.dump(comments, file)
        return result

class ForumDb(Db):
    def __init__(self, path : str, port_api : int, port_tcp : int):
        super().__init__(path, port_api, port_tcp)
    
    def create_forum_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS forums (
        fid INTEGER UNIQUE NOT NULL,
        forumname TEXT NOT NULL,
        creater INTEGER,
        create_time REAL,
        introduction TEXT,
        post_num INTEGER,
        pinned_pid INTEGER DEFAULT NULL
    )
    """
        cmd2 = """
    CREATE TABLE IF NOT EXISTS contents (
        fid INTEGER NOT NULL,
        pid INTEGER UNIQUE NOT NULL,
        title TEXT,
        creater INTEGER NOT NULL,
        content TEXT,
        send_time REAL
    )
    """
        self.execute(cmd)
        self.execute(cmd2)
        try:
            self.execute("ALTER TABLE forums ADD COLUMN pinned_pid INTEGER DEFAULT NULL")
        except Exception:
            pass
        self.execute("""
    CREATE TABLE IF NOT EXISTS forum_members (
        fid INTEGER NOT NULL,
        uid INTEGER NOT NULL,
        role INTEGER DEFAULT 0,
        join_time REAL,
        PRIMARY KEY (fid, uid)
    )
    """)
    
    def create_forum(self, forumname, creater : int, introduction):
        """
        创建论坛
        
        :param forumname: 论坛名
        :param creater: 创建者（uid）
        :param introduction: 论坛简介
        """
        cmd = """
    CREATE TABLE IF NOT EXISTS F{} (
        time_stamp REAL,
        content TEXT
    )"""
        def insert_forum():
            self.cursor.execute("SELECT MAX(fid) from forums")
            fid = self.cursor.fetchone()[0]
            if fid == None:
                fid = 0
            else:
                fid += 1
            self.cursor.execute(
                "INSERT INTO forums (fid, forumname, creater, create_time, introduction, post_num) VALUES (?, ?, ?, ?, ?, 0)",
                (fid, forumname, creater, time(), introduction)
            )
            self.cursor.execute(cmd.format(fid))
            self.cursor.execute(
                "INSERT INTO forum_members (fid, uid, role, join_time) VALUES (?, ?, 100, ?)",
                (fid, creater, time())
            )
            self.conn.commit()
            return fid

        with self.lock:
            fid = self._execute_with_retry(insert_forum)

        update_comments(self.api_pt, lambda comments: comments.setdefault(str(fid), {}))
        return fid
    
    def query_forum_fid(self, fid):
        return self.query("SELECT * FROM forums WHERE fid = ?", (fid,))
    
    def query_forum_forumname(self, forumname):
        return self.query("SELECT * FROM forums WHERE forumname LIKE ?", ('%' + forumname + '%', ))
    
    def query_forum_creater(self, creater : int):
        return self.query("SELECT * FROM forums WHERE creater = ?", (creater,))
    
    def query_post_pid(self, fid : int, pid : int):
        return self.query("SELECT * FROM contents WHERE pid = ? and fid = ?", (pid, fid))
    
    def query_post_title(self, fid : int, title : str):
        return self.query("SELECT * FROM contents WHERE fid = ? and title LIKE ?", (fid, '%' + title + '%',))
    
    def query_post_content(self, fid : int, content : str):
        return self.query("SELECT * FROM contents WHERE fid = ? and content LIKE ?", (fid, '%' + content + '%', ))
    
    def query_post_sender(self, fid : int, sender : int):
        return self.query("SELECT * FROM contents WHERE fid = ? and creater = ?", (fid, sender, ))
    
    def query_all_post(self, fid):
        return self.query("SELECT * FROM contents WHERE fid = ?", (fid, ))
    
    def query_all_forums(self):
        return self.query("SELECT * FROM forums ORDER BY post_num DESC")

    def send_post(self, fid : int, sender : int, title : str, content : str):
        if len(title) > 30:
            return False
        def insert_post():
            self.cursor.execute("SELECT MAX(pid) from contents")
            pid = self.cursor.fetchone()[0]
            if pid == None:
                pid = 0
            else:
                pid += 1
            self.cursor.execute(
                "INSERT INTO contents (fid, pid, title, creater, content, send_time) VALUES (?, ?, ?, ?, ?, ?)",
                (fid, pid, title, sender, content, time())
            )
            self.cursor.execute("UPDATE forums set post_num = post_num + 1 where fid = ?", (fid,))
            self.conn.commit()
            return pid

        with self.lock:
            pid = self._execute_with_retry(insert_post)

        def add_post_bucket(comments):
            comments.setdefault(str(fid), {})[str(pid)] = {}

        try:
            update_comments(self.api_pt, add_post_bucket)
        except Exception as e:
            print("[WARN] send_post: comments JSON 更新失败 fid={} pid={}: {}".format(fid, pid, e))
        return True
    
    def pin_post(self, fid : int, pid : int):
        if not self.query_post_pid(fid, pid):
            return False
        self.execute("UPDATE forums SET pinned_pid = ? WHERE fid = ?", (pid, fid))
        return True

    def unpin_post(self, fid : int):
        self.execute("UPDATE forums SET pinned_pid = NULL WHERE fid = ?", (fid,))
        return True

    def get_pinned_pid(self, fid : int):
        try:
            row = self.query("SELECT pinned_pid FROM forums WHERE fid = ?", (fid,))
            if row and row[0][0] is not None:
                return row[0][0]
        except Exception:
            pass
        return None

    def add_member(self, fid : int, uid : int, role : int = 0):
        self.execute(
            "INSERT OR REPLACE INTO forum_members (fid, uid, role, join_time) VALUES (?, ?, ?, ?)",
            (fid, uid, role, time())
        )
        return True

    def remove_member(self, fid : int, uid : int):
        self.execute(
            "DELETE FROM forum_members WHERE fid = ? AND uid = ?", (fid, uid)
        )
        return True

    def change_member_role(self, fid : int, uid : int, role : int):
        self.execute(
            "UPDATE forum_members SET role = ? WHERE fid = ? AND uid = ?",
            (role, fid, uid)
        )
        return True

    def list_members(self, fid : int):
        return self.query(
            "SELECT fid, uid, role, join_time FROM forum_members WHERE fid = ? ORDER BY role DESC",
            (fid,)
        )

    def get_member_role(self, fid : int, uid : int):
        row = self.query(
            "SELECT role FROM forum_members WHERE fid = ? AND uid = ?", (fid, uid)
        )
        if row:
            return row[0][0]
        return None

    def is_member(self, fid : int, uid : int):
        return self.get_member_role(fid, uid) is not None

    def delete_forum(self, fid : int):
        self.execute("DELETE FROM forums WHERE fid = ?", (fid, ))
        self.execute("DELETE FROM contents WHERE fid = ?", (fid, ))
        self.execute("DELETE FROM forum_members WHERE fid = ?", (fid, ))
        self.execute("DROP TABLE IF EXISTS F{}".format(fid))
        update_comments(self.api_pt, lambda comments: comments.pop(str(fid), None))

    def delete_post(self, fid : int, pid : int):
        if not self.query_post_pid(fid, pid):
            return
        def do_delete():
            self.cursor.execute("DELETE FROM contents where pid = ?", (pid,))
            self.cursor.execute(
                "UPDATE forums set post_num = CASE WHEN post_num > 0 THEN post_num - 1 ELSE 0 END where fid = ?",
                (fid,)
            )
            self.conn.commit()

        with self.lock:
            self._execute_with_retry(do_delete)

        def remove_post_bucket(comments):
            forum_comments = comments.get(str(fid))
            if isinstance(forum_comments, dict):
                forum_comments.pop(str(pid), None)

        try:
            update_comments(self.api_pt, remove_post_bucket)
        except Exception as e:
            print("[WARN] delete_post: comments JSON 更新失败 fid={} pid={}: {}".format(fid, pid, e))

    def clean_user_content(self, uid : int):
        uid = int(uid)
        with self.lock:
            def operation():
                self.cursor.execute("DELETE FROM forum_members WHERE uid = ?", (uid,))
                self.cursor.execute("SELECT fid FROM forums WHERE creater = ?", (uid,))
                deleted_forums = [row[0] for row in self.cursor.fetchall()]

                for fid in deleted_forums:
                    self.cursor.execute("DELETE FROM forums WHERE fid = ?", (fid,))
                    self.cursor.execute("DELETE FROM contents WHERE fid = ?", (fid, ))
                    self.cursor.execute("DELETE FROM forum_members WHERE fid = ?", (fid,))
                    self.cursor.execute("DROP TABLE IF EXISTS F{}".format(fid))

                self.cursor.execute("SELECT fid FROM forums")
                remaining_forums = [row[0] for row in self.cursor.fetchall()]
                deleted_posts = {}

                for fid in remaining_forums:
                    self.cursor.execute("SELECT pid FROM contents WHERE creater = ? and fid = ?", (uid, fid))
                    post_ids = [row[0] for row in self.cursor.fetchall()]
                    if not post_ids:
                        continue

                    deleted_posts[fid] = post_ids
                    self.cursor.execute("DELETE FROM contents WHERE creater = ? and fid = ?", (uid, fid))
                    self.cursor.execute(
                        "UPDATE forums SET post_num = CASE WHEN post_num >= ? THEN post_num - ? ELSE 0 END WHERE fid = ?",
                        (len(post_ids), len(post_ids), fid),
                    )

                self.conn.commit()
                return deleted_forums, deleted_posts

            deleted_forums, deleted_posts = self._execute_with_retry(operation)

        deleted_posts_text = {
            str(fid): {str(pid) for pid in post_ids}
            for fid, post_ids in deleted_posts.items()
        }

        def clean_comments(comments):
            for fid in deleted_forums:
                comments.pop(str(fid), None)

            for fid, forum_comments in list(comments.items()):
                if not isinstance(forum_comments, dict):
                    continue

                removed_posts = deleted_posts_text.get(fid, set())
                for pid in list(forum_comments.keys()):
                    if pid in removed_posts:
                        forum_comments.pop(pid, None)
                        continue

                    thread = forum_comments.get(pid)
                    if not isinstance(thread, dict):
                        continue

                    for time_stamp, entry in list(thread.items()):
                        if isinstance(entry, list) and entry and entry[0] == uid:
                            del thread[time_stamp]

            return True

        update_comments(self.api_pt, clean_comments)
        return True