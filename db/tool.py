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
        self._local = threading.local()
        self._init_thread()

    def _init_thread(self):
        conn = sqlite3.connect(self.path, timeout=10)
        if self.WAL_mode:
            conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        self._local.conn = conn
        self._local.cursor = conn.cursor()

    @property
    def conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._init_thread()
        return self._local.conn

    @property
    def cursor(self):
        if not hasattr(self._local, 'cursor') or self._local.cursor is None:
            self._init_thread()
        return self._local.cursor

    def _reconnect(self):
        try:
            if hasattr(self._local, 'conn') and self._local.conn:
                self._local.conn.close()
        except Exception:
            pass
        self._local.conn = None
        self._local.cursor = None
        self._init_thread()

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
                lastrowid = self.cursor.lastrowid
                self.conn.commit()
                return lastrowid
            return self._execute_with_retry(operation)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if hasattr(self._local, 'conn') and self._local.conn:
                self._local.conn.close()
        except Exception:
            pass
