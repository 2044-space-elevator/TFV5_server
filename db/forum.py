from db.tool import Db
from time import time
import json

class ForumDb(Db):
    def __init__(self, path : str, port_api : int, port_tcp : int):
        super().__init__(path, port_api, port_tcp)
    
    def create_forum_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS forums (
        fid INTEGER UNIQUE NOT NULL,
        forumname TEXT NOT NULL,
        creater INTEGER,
        create_time TEXT REAL,
        introduction TEXT,
        post_num INTEGER
    )
    """
        self.execute(cmd)
    
    def create_forum(self, forumname, creater : int, introduction):
        """
        创建论坛
        
        :param forumname: 论坛名
        :param creater: 创建者（uid）
        :param introduction: 论坛简介
        """
        fid = self.query("SELECT MAX(fid) from forums")[0][0]
        if fid == None:
            fid = 0
        else:
            fid += 1
        
        cmd = """
    CREATE TABLE IF NOT EXISTS F{} (
        pid INTEGER UNIQUE NOT NULL,
        title TEXT,
        creater INTEGER NOT NULL,
        content TEXT,
        send_time TEXT REAL
    )  
    """
        self.execute("INSERT INTO forums (fid, forumname, creater, create_time, introduction, post_num) VALUES (?, ?, ?, ?, ?, 0)", (fid, forumname, creater, time(), introduction))
        self.execute(cmd.format(fid))
        with open("res/{}/forum/comments.json".format(self.api_pt), "r+") as file:
            comments = json.load(file)
        comments[fid] = {}
        with open("res/{}/forum/comments.json".format(self.api_pt), "w+") as file:
            json.dump(comments, file)
    
    def query_forum_fid(self, fid):
        return self.query("SELECT * FROM forums WHERE fid = ?", (fid,))
    
    def query_forum_forumname(self, forumname):
        return self.query("SELECT * FROM forums WHERE forumname LIKE ?", ('%' + forumname + '%', ))
    
    def query_forum_creater(self, creater : int):
        return self.query("SELECT * FROM forums WHERE creater = ?", (creater,))
    
    def query_post_pid(self, fid : int, pid : int):
        return self.query("SELECT * FROM F{} WHERE pid = ?".format(fid), (pid,))
    
    def query_post_title(self, fid : int, title : str):
        return self.query("SELECT * FROM F{} WHERE title LIKE ?".format(fid), ('%' + title + '%',))
    
    def query_post_content(self, fid : int, content : str):
        return self.query("SELECT * FROM F{} WHERE content LIKE ?".format(fid), ('%' + content + '%', ))
    
    def query_post_sender(self, fid : int, sender : int):
        return self.query("SELECT * FROM F{} WHERE creater = ?".format(fid), (sender, ))
    
    def query_all_post(self, fid):
        return self.query("SELECT * FROM F{}".format(fid))
    
    def query_all_forums(self):
        return self.query("SELECT * FROM forums ORDER BY post_num DESC")

    def send_post(self, fid : int, sender : int, title : str, content : str):
        if len(title) > 30:
            return False
        pid = self.query("SELECT MAX(pid) from F{}".format(fid))[0][0]
        if pid == None:
            pid = 0
        else:
            pid += 1
        self.execute("INSERT INTO F{} (pid, title, creater, content, send_time) VALUES (?, ?, ?, ?, ?)".format(fid), (pid, title, sender, content, time()))
        self.execute("UPDATE forums set post_num = post_num + 1 where fid = ?", (fid,))
        with open("res/{}/forum/comments.json".format(self.api_pt), "r+") as file:
            comments = json.load(file)
        comments[str(fid)][str(pid)] = {}
        with open("res/{}/forum/comments.json".format(self.api_pt), "w+") as file:
            json.dump(comments, file)
        return True
    
    def delete_forum(self, fid : int):
        self.execute("DELETE FROM forums WHERE fid = ?", (fid, ))
        self.execute("DROP TABLE IF EXISTS F{}".format(fid))
        with open("res/{}/forum/comments.json".format(self.api_pt), "r+") as file:
            comments = json.load(file)
        del comments[str(fid)]
        with open("res/{}/forum/comments.json".format(self.api_pt), "w+") as file:
            json.dump(comments, file)

    def delete_post(self, fid : int, pid : int):
        self.execute("DELETE FROM F{} where pid = ?".format(fid), (pid,))
        with open("res/{}/forum/comments.json".format(self.api_pt), "r+") as file:
            comments = json.load(file)
        del comments[str(fid)][str(pid)]
        with open("res/{}/forum/comments.json".format(self.api_pt), "w+") as file:
            json.dump(comments, file)