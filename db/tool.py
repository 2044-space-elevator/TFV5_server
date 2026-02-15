import sqlite3
import threading
import time

class Db:
    def __init__(self, path: str, PORT_API: int, PORT_TCP: int, WAL_mode=True, max_retries=3):
        self.path = path
        self.api_pt = PORT_API
        self.tcp_pt = PORT_TCP
        self.WAL_mode = WAL_mode
        self.max_retries = max_retries          
        self.lock = threading.Lock()
        self._connect()                         

    def _connect(self):
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        if self.WAL_mode:
            self.cursor.execute('PRAGMA journal_mode=WAL')

    def _reconnect(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self._connect()

    def _execute_with_retry(self, db_operation, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return db_operation(*args, **kwargs)
            except (sqlite3.OperationalError, sqlite3.ProgrammingError) as e:
                if attempt == self.max_retries - 1:
                    raise  
                self._reconnect()
                time.sleep(0.1)   
            except Exception:
                raise

    def update(self, command: str, parameters: list):
        with self.lock:
            def operation():
                self.cursor.executemany(command, parameters)
                self.conn.commit()
            self._execute_with_retry(operation)

    def query(self, command: str, parameters: tuple = None):
        with self.lock:
            def operation():
                if parameters:
                    self.cursor.execute(command, parameters)
                else:
                    self.cursor.execute(command)
                return self.cursor.fetchall()
            return self._execute_with_retry(operation)

    def execute(self, command: str, parameters: tuple = None):
        with self.lock:
            def operation():
                if parameters:
                    self.cursor.execute(command, parameters)
                else:
                    self.cursor.execute(command)
                self.conn.commit()
            self._execute_with_retry(operation)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()