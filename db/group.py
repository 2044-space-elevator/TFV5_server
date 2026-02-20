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
    
    def groupname_search(self, groupname : str):
        return self.query("SELECT * FROM groups WHERE groupname LIKE ?", ('%' + groupname + '%',))
    
    def is_admin(self, gid : int, uid : int):
        members = self.query_gid(gid)
        creater, admins = members[0][1], members[0][4]
        admins = json.loads(admins)
        if uid in admins:
            return 1
        if uid == creater:
            return 2
        return 0
    
    def edit_enter_hint(self, gid : int, enter_hint : str):
        self.execute('UPDATE groups SET enter_hint = ? WHERE gid = ?', (enter_hint, gid))
    
    def edit_introduction(self, gid : int, introduction : str):
        self.execute('UPDATE groups SET introduction = ? WHERE gid = ?', (introduction, gid))
    
    def query_gid(self, gid : int):
        return self.query("SELECT * FROM groups WHERE gid = ?", (gid,))
    
    def remove_member(self, gid : int, member : int):
        members = self.query("SELECT * FROM groups WHERE gid = ?", (gid,))
        if len(members) < 1:
            return False
        creater, members, admins = members[0][1], members[0][3], members[0][4]
        members = json.loads(members)
        admins = json.loads(admins)
        if member not in members:
            return False
        
        if creater == member:
            return False
        members.remove(member)
        if member in admins:
            admins.remove(member)
            self.execute("UPDATE groups SET admins = ? WHERE gid = ?", (str(admins), gid))
        self.execute("UPDATE groups SET members = ? WHERE gid = ?", (str(members), gid))
        return True
    
    def add_admin(self, gid : int, member : int):
        members = self.query("SELECT * FROM groups WHERE gid = ?", (gid,))
        if len(members) < 1:
            return False
        creater, members, admins = members[0][1], members[0][3], members[0][4]
        members = json.loads(members)
        admins = json.loads(admins)
        if creater == member:
            return False
        if member not in members:
            return False
        if member in admins:
            return False
        admins.append(member)
        self.execute("UPDATE groups SET admins = ? WHERE gid = ?", (str(admins), gid))
        return True
    
    def remove_admin(self, gid : int, member : int):
        members = self.query("SELECT * FROM groups WHERE gid = ?", (gid,))
        if len(members) < 1:
            return False
        admins = members[0][4]
        admins = json.loads(admins)
        if not member in admins:
            return False
        admins.remove(member)
        self.execute("UPDATE groups SET admins = ? WHERE gid = ?", (str(admins), gid))
        return True

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
        self.execute('INSERT INTO groups (gid, creater, groupname, members, admins, enter_hint, introduction) VALUES (?, ?, ?, "[{}]", "[]", ?, ?)'.format(creater), (gid, creater, groupname, enter_hint, introduction))
        self.execute(cmd.format(gid))
        return True
    
    def add_member(self, gid : int, new_memeber : int):
        members = self.query("SELECT * FROM groups WHERE gid = ?", (gid,))
        if len(members) < 1:
            return False
        members = json.loads(members[0][3])
        if new_memeber in members:
            return False
        members.append(new_memeber)
        self.execute("UPDATE groups SET members = ? WHERE gid = ?", (str(members), gid))
        return True
    
    def delete_group(self, gid : int):
        self.execute("DROP TABLE IF EXISTS G{}".format(gid))
        self.execute("DELETE FROM groups WHERE gid = ?", (gid,))