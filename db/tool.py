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
        # 写锁：串行化所有写操作。读操作在 WAL 模式下并发，不加这把锁。
        self.lock = threading.Lock()
        # 每线程一个独立连接，避免单连接 + 单锁把读也串行化。
        self._local = threading.local()
        # 初始化主线程连接（触发 WAL 等 PRAGMA）。
        _ = self.conn

    def _connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        if self.WAL_mode:
            conn.execute("PRAGMA journal_mode=WAL")
        # WAL + synchronous=NORMAL：写性能大幅提升，崩溃时最多丢最后一次事务。
        conn.execute("PRAGMA synchronous=NORMAL")
        # 写冲突时等待而不是立刻报错。
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @property
    def conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
            self._local.cursor = conn.cursor()
        return conn

    @property
    def cursor(self):
        _ = self.conn
        return self._local.cursor

    def _reconnect(self):
        try:
            if getattr(self._local, "conn", None) is not None:
                self._local.conn.close()
        except Exception:
            pass
        self._local.conn = self._connect()
        self._local.cursor = self._local.conn.cursor()

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
        # 读操作不加锁：每个线程用自己的连接，WAL 下可并行读取。
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
            if getattr(self._local, "conn", None) is not None:
                self._local.conn.close()
        except Exception:
            pass
