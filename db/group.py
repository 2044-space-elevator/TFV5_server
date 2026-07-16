from db.tool import Db
import json
import time


class GroupDb(Db):
    def __init__(self, path: str, port_api: int, config_reader=None):
        super().__init__(path, port_api, -1)
        self._config_reader = config_reader or self._default_config_reader
        self.create_group_table()

    def _default_config_reader(self):
        with open("res/{}/config.json".format(self.api_pt), "r+") as f:
            return json.load(f)

    def create_group_table(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                gid INTEGER UNIQUE NOT NULL,
                creater INTEGER NOT NULL,
                groupname TEXT,
                members TEXT,
                admins TEXT,
                enter_hint TEXT,
                introduction TEXT,
                allow_direct_join INTEGER NOT NULL DEFAULT 0,
                require_review INTEGER NOT NULL DEFAULT 1
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS join_requests (
                rid INTEGER PRIMARY KEY AUTOINCREMENT,
                gid INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                inviter_uid INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                request_time REAL NOT NULL
            )
        """)
        self._migrate()

    def _migrate(self):
        from sqlite3 import OperationalError
        try:
            self.execute("ALTER TABLE groups ADD COLUMN allow_direct_join INTEGER NOT NULL DEFAULT 0")
        except OperationalError:
            pass
        try:
            self.execute("ALTER TABLE groups ADD COLUMN require_review INTEGER NOT NULL DEFAULT 1")
        except OperationalError:
            pass

    def query_gid(self, gid: int):
        return self.query("SELECT * FROM groups WHERE gid = ?", (gid,))

    def query_creater(self, uid: int):
        return self.query("SELECT * FROM groups WHERE creater = ?", (uid,))

    def groupname_search(self, groupname: str):
        return self.query("SELECT * FROM groups WHERE groupname LIKE ?",
                          ('%' + groupname + '%',))

    def get_member_uids(self, gid: int) -> list:
        row = self.query_gid(gid)
        if not row:
            return []
        return json.loads(row[0][3])

    def get_admin_uids(self, gid: int) -> list:
        row = self.query_gid(gid)
        if not row:
            return []
        return json.loads(row[0][4])

    def is_admin(self, gid: int, uid: int) -> int:
        """0=member, 1=admin, 2=owner."""
        row = self.query_gid(gid)
        if not row:
            return 0
        creater, admins = row[0][1], json.loads(row[0][4])
        if uid == creater:
            return 2
        if uid in admins:
            return 1
        return 0

    def is_member(self, gid: int, uid: int) -> bool:
        members = self.get_member_uids(gid)
        return uid in members

    def get_group_settings(self, gid: int) -> dict:
        row = self.query_gid(gid)
        if not row:
            return {}
        r = row[0]
        return {
            "gid": r[0], "creater": r[1], "groupname": r[2],
            "enter_hint": r[5], "introduction": r[6],
            "allow_direct_join": bool(r[7]), "require_review": bool(r[8]),
        }

    def get_user_group_rows(self, uid: int) -> list:
        rows = self.query("SELECT * FROM groups")
        result = []
        for row in rows:
            try:
                members = json.loads(row[3])
            except Exception:
                continue
            if uid in members:
                result.append(row)
        return result

    def get_user_groups(self, uid: int) -> list:
        return [
            {"gid": row[0], "groupname": row[2]}
            for row in self.get_user_group_rows(uid)
        ]

    def create_group(self, creater: int, groupname: str, enter_hint: str,
                     introduction: str, allow_direct_join: bool = False,
                     require_review: bool = True) -> int:
        cfg = self._config_reader()
        created = self.query_creater(creater)
        limit = cfg.get("groups_limit", 30)
        if limit != -1 and len(created) >= limit:
            return 0

        gid = self.query("SELECT COALESCE(MAX(gid), 0) FROM groups")[0][0] + 1
        self.execute(
            """INSERT INTO groups (gid, creater, groupname, members, admins,
               enter_hint, introduction, allow_direct_join, require_review)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gid, creater, groupname, json.dumps([creater]), json.dumps([]),
             enter_hint, introduction,
             int(allow_direct_join), int(require_review))
        )
        return gid

    def delete_group(self, gid: int):
        self.execute("DELETE FROM join_requests WHERE gid = ?", (gid,))
        self.execute("DELETE FROM groups WHERE gid = ?", (gid,))

    def add_member(self, gid: int, new_member: int) -> bool:
        row = self.query_gid(gid)
        if not row:
            return False
        members = json.loads(row[0][3])
        if new_member in members:
            return False

        cfg = self._config_reader()
        limit = cfg.get("single_group_max_people", 200)
        if limit != -1 and len(members) >= limit:
            return False

        members.append(new_member)
        self.execute("UPDATE groups SET members = ? WHERE gid = ?",
                     (json.dumps(members), gid))
        return True

    def remove_member(self, gid: int, member: int) -> bool:
        row = self.query_gid(gid)
        if not row:
            return False
        creater, members, admins = row[0][1], json.loads(row[0][3]), json.loads(row[0][4])
        if member not in members:
            return False
        if creater == member:
            return False  # tf owner 必须保留
        members.remove(member)
        if member in admins:
            admins.remove(member)
            self.execute("UPDATE groups SET admins = ? WHERE gid = ?",
                         (json.dumps(admins), gid))
        self.execute("UPDATE groups SET members = ? WHERE gid = ?",
                     (json.dumps(members), gid))
        return True
    def add_admin(self, gid: int, uid: int) -> bool:
        row = self.query_gid(gid)
        if not row:
            return False
        creater, members, admins = row[0][1], json.loads(row[0][3]), json.loads(row[0][4])
        if uid == creater or uid not in members or uid in admins:
            return False
        admins.append(uid)
        self.execute("UPDATE groups SET admins = ? WHERE gid = ?",
                     (json.dumps(admins), gid))
        return True

    def remove_admin(self, gid: int, uid: int) -> bool:
        row = self.query_gid(gid)
        if not row:
            return False
        admins = json.loads(row[0][4])
        if uid not in admins:
            return False
        admins.remove(uid)
        self.execute("UPDATE groups SET admins = ? WHERE gid = ?",
                     (json.dumps(admins), gid))
        return True

    def transfer_owner(self, gid: int, old_owner: int, new_owner: int) -> bool:
        row = self.query_gid(gid)
        if not row:
            return False
        creater = row[0][1]
        if creater != old_owner:
            return False
        members = json.loads(row[0][3])
        if new_owner not in members:
            return False
        admins = json.loads(row[0][4])
        if new_owner in admins:
            admins.remove(new_owner)
        if old_owner not in admins:
            admins.append(old_owner)
        self.execute("UPDATE groups SET creater = ?, admins = ? WHERE gid = ?",
                     (new_owner, json.dumps(admins), gid))
        return True

    # --- group settings ---

    def update_settings(self, gid: int, **kwargs) -> bool:
        allowed = {"groupname", "enter_hint", "introduction",
                   "allow_direct_join", "require_review"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if "allow_direct_join" in updates:
            updates["allow_direct_join"] = int(updates["allow_direct_join"])
        if "require_review" in updates:
            updates["require_review"] = int(updates["require_review"])
        set_clause = ", ".join("{} = ?".format(k) for k in updates)
        self.execute(
            "UPDATE groups SET {} WHERE gid = ?".format(set_clause),
            tuple(updates.values()) + (gid,)
        )
        return True


    def request_join(self, gid: int, uid: int, inviter_uid: int = 0) -> int:
        """创建一个加入请求，如果已经存在 pending 请求则返回现有请求的 rid，否则创建新请求并返回新 rid。"""
        existing = self.query(
            "SELECT rid FROM join_requests WHERE gid = ? AND uid = ? AND status = 'pending'",
            (gid, uid)
        )
        if existing:
            return existing[0][0]
        self.execute(
            """INSERT INTO join_requests (gid, uid, inviter_uid, status, request_time)
               VALUES (?, ?, ?, 'pending', ?)""",
            (gid, uid, inviter_uid, time.time())
        )
        return self.cursor.lastrowid

    def get_join_requests(self, gid: int, status: str = 'pending') -> list:
        rows = self.query(
            """SELECT rid, gid, uid, inviter_uid, status, request_time
               FROM join_requests WHERE gid = ? AND status = ? ORDER BY request_time DESC""",
            (gid, status)
        )
        return [
            {"rid": r[0], "gid": r[1], "uid": r[2], "inviter_uid": r[3],
             "status": r[4], "request_time": r[5]}
            for r in rows
        ]

    def handle_join_request(self, rid: int, approved: bool) -> bool:
        row = self.query(
            "SELECT gid, uid, status FROM join_requests WHERE rid = ?", (rid,)
        )
        if not row or row[0][2] != 'pending':
            return False
        gid, uid = row[0][0], row[0][1]
        if not approved:
            self.execute("UPDATE join_requests SET status = 'rejected' WHERE rid = ?", (rid,))
            return True
        if not self.add_member(gid, uid):
            return False
        self.execute("UPDATE join_requests SET status = 'approved' WHERE rid = ?", (rid,))
        return True

    # --- user removal (admin tool) ---

    def remove_user_membership(self, uid: int):
        with self.lock:
            def operation():
                self.cursor.execute("SELECT gid, creater, members, admins FROM groups")
                groups = self.cursor.fetchall()
                deleted_gids = []
                for gid, creater, members_raw, admins_raw in groups:
                    if creater == uid:
                        self.cursor.execute("DELETE FROM join_requests WHERE gid = ?", (gid,))
                        self.cursor.execute("DELETE FROM groups WHERE gid = ?", (gid,))
                        deleted_gids.append(gid)
                        continue
                    members = json.loads(members_raw)
                    admins = json.loads(admins_raw)
                    changed = False
                    if uid in members:
                        members = [m for m in members if m != uid]
                        changed = True
                    if uid in admins:
                        admins = [a for a in admins if a != uid]
                        changed = True
                    if changed:
                        self.cursor.execute(
                            "UPDATE groups SET members = ?, admins = ? WHERE gid = ?",
                            (json.dumps(members), json.dumps(admins), gid),
                        )
                self.conn.commit()
                return deleted_gids
            return self._execute_with_retry(operation)
