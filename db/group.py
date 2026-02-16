from db.tool import Db
import json

class GroupDb(Db):
    def __init__(self, path : str, port_api : int):
        super().__init__(path, port_api, -1)
    
    def create_group_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS groups (
        gid INTEGER UNIQUE NOT NULL,
        creater INTEGER NOT NULL,
        groupname TEXT,
        members TEXT,
        admins TEXT,
        enter_hint TEXT,
        introduction TEXT
    )
    """
        self.execute(cmd)

    def query_creater(self, uid : int):
        return self.query("SELECT * FROM groups WHERE creater = ?", (uid,))

    def create_group(self, creater : int, groupname : str, enter_hint : str, introduction : str):
        cmd = """
    CREATE TABLE IF NOT EXISTS G{} (
        time_stamp REAL,
        content TEXT 
    )""" 
        with open("res/{}/config.json".format(self.api_pt), "r+") as file:
            cfg = json.load(file)
        created_by = self.query_creater(creater)
        if len(created_by) >= cfg["groups_limit"]:
            return False
        gid = self.query("SELECT MAX(gid) from groups")[0][0]
        if gid == None:
            gid = 0
        else:
            gid += 1
        self.execute('INSERT INTO groups (gid, creater, groupname, members, admins, enter_hint, introduction) VALUES (?, ?, ?, "[]", "[]", ?, ?)', (gid, creater, groupname, enter_hint, introduction))
        self.execute(cmd.format(gid))
        return True
    
    def delete_group(self, gid : int):
        self.execute("DROP TABLE IF EXISTS G{}".format(gid))
        self.execute("DELETE FROM groups WHERE gid = ?", (gid,))