import sqlite3
import threading

class Db:
    def __init__(self, path : str, PORT_API : int, PORT_TCP : int, WAL_mode=True):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()
        self.api_pt = PORT_API
        self.tcp_pt = PORT_TCP
        if WAL_mode:
            self.cursor.execute('PRAGMA journal_mode=WAL')
    
    def __enter__(self):
        return self

    def __exit__(self):
        if self.conn:
            self.conn.close()
    
    def update(self, command : str, parameters: list):
        with self.lock:
            try:
                self.cursor.executemany(command, parameters)
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                raise e
    
    def query(self, command : str, parameters : tuple = None):
        with self.lock:
            if parameters:
                self.cursor.execute(command, parameters)
            else:
                self.cursor.execute(command)
            return self.cursor.fetchall()
    
    def execute(self, command: str, parameters: tuple = None):
        with self.lock:
            if parameters:
                self.cursor.execute(command, parameters)
            else:
                self.cursor.execute(command)
        self.conn.commit()
    