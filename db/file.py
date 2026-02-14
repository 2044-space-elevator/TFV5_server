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
        active BOOLEAN
    )
    """
        self.execute(cmd)
    
    def tag_file(self, sender : int, file_name : str, send_time : str, hashes : str):
        self.execute("INSERT into file (sender, file_name, send_time, hash, active) VALUES (?, ?, ?, ?, TRUE)", (sender, file_name, send_time, hashes))
    
    def lose_effect(self):
        time_end = time.time()
        with open("res/{}/config.json".format(self.api_pt), "r+") as file:
            time_end -= json.load(file)["file_last_time"] * 3600
        query_ans = self.query("SELECT * FROM file WHERE send_time < ? and active = TRUE", (time_end, ))
        self.execute("UPDATE file SET active = FALSE WHERE send_time < ?", (time_end,))
        return query_ans

    def return_file(self, hashes : str):
        return self.query("SELECT * FROM file WHERE hash = ?", (hashes,))