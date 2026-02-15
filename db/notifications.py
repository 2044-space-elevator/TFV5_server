from tool import Db 
import time

class NotificationsDb(Db):
    def __init__(self, path : str, port_api : int):
        super().__init__(path, port_api, -1)
    
    def create_usre_table(self, uid : int):
        cmd = """
    CREATE TABLE IF NOT EXISTS U{} (
        time_stamp REAL,
        info TEXT
    )
    """.format(uid)
        self.execute(cmd)

    def query_events_after(self, uid : int, time_stamp : str):
        return self.query("SELECT * FROM U{} WHERE time_stamp > ?".format(uid), (time_stamp,))

    def add_event(self, uid : int, event : str):
        self.execute("INSERT INTO U{} (time_stamp, info) VALUES (?, ?)".format(uid), (time.time(), event))