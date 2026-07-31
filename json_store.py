import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager


_thread_locks = {}
_thread_locks_guard = threading.Lock()


def _thread_lock(path):
    absolute_path = os.path.abspath(path)
    with _thread_locks_guard:
        return _thread_locks.setdefault(absolute_path, threading.Lock())


@contextmanager
def _file_lock(path):
    lock_path = os.path.abspath(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with _thread_lock(path):
        lock_file = open(lock_path, "a+b")
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt

                if os.path.getsize(lock_path) == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                while True:
                    try:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                        break
                    except OSError:
                        time.sleep(0.01)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                acquired = True
            yield
        finally:
            if acquired and os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            elif acquired:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


def _write_unlocked(path, value):
    absolute_path = os.path.abspath(path)
    directory = os.path.dirname(absolute_path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".json-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, absolute_path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def read_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    with _file_lock(path):
        _write_unlocked(path, value)


_MISSING = object()


def update_json(path, mutator, default=_MISSING):
    with _file_lock(path):
        try:
            value = read_json(path)
        except FileNotFoundError:
            if default is _MISSING:
                raise
            value = default() if callable(default) else default
        result = mutator(value)
        _write_unlocked(path, value)
        return result
