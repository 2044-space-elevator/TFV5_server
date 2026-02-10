from db.tool import Db
import json

class ForumDb(Db):
    def __init__(self, path : str, port_api : int, port_tcp : int):
        super().__init__(path, port_api, port_tcp)
    
    def create_forum_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS forums (
        fid INTEGER UNIQUE NOT NULL,
        forumname TEXT NOT NULL,
        creater TEXT NOT NULL,
        create_time TEXT REAL,
        introdution TEXT
    )
    """
        self.execute(cmd)