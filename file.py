from __future__ import annotations
import os
import base64
import time
from db import FileDb
import hashlib
from file_types import detect_file_type
import threading

_upload_lock = threading.Lock()

def sha256(data : str | bytes) -> str:
    if isinstance(data, str):
        data = bytes(data, encoding="utf-8")

    sha256_hash = hashlib.sha256()
    sha256_hash.update(data)

    return sha256_hash.hexdigest()

def init(port_api : int):
    if not os.path.exists("res/{}/file".format(port_api)):
        os.makedirs("res/{}/file".format(port_api))
    file_cursor = FileDb("res/{}/file/file.db".format(port_api), port_api)
    file_cursor.create_file_db()


def file_path(port_api : int, hashes : str):
    return "res/{}/file/{}.file".format(port_api, hashes)

def upload_file(port_api : int, uid : int, file_b64 : str, file_name : str, file_cursor : FileDb, file_last_time : float = 72.0):
    content = base64.b64decode(file_b64)
    file_size = len(content)
    hashes = sha256(content)
    file_type = detect_file_type(content, file_name)
    extension = os.path.splitext(file_name)[1].lower()

    disk_path = file_path(port_api, hashes)
    with _upload_lock:
        wrote_blob = False
        try:
            registered = file_cursor.file_exists(hashes)
            if not registered or not os.path.isfile(disk_path):
                with open(disk_path, "wb") as file:
                    wrote_blob = True
                    file.write(content)

            file_cursor.register_upload(
                uid, hashes, file_name, time.time(), file_size,
                mime_type=file_type, extension=extension,
            )
        except Exception:
            if wrote_blob:
                try:
                    registered = file_cursor.file_exists(hashes)
                except Exception:
                    registered = True
                if not registered and os.path.isfile(disk_path):
                    try:
                        os.remove(disk_path)
                    except OSError:
                        pass
            raise

    return hashes

def dereference_file(port_api : int, uid : int, hashes : str, file_cursor : FileDb, file_last_time : float = 72.0):
    return delete_user_file(port_api, uid, hashes, file_cursor)

def delete_user_file(port_api : int, uid : int, hashes : str, file_cursor : FileDb):
    succeeded, deleted = file_cursor.delete_owned_user_file(uid, hashes)
    if not succeeded:
        return False
    # 存储空间回收
    if deleted:
        file_cursor.delete_blob_relations(hashes)
        target_path = file_path(port_api, hashes)
        if os.path.isfile(target_path):
            os.remove(target_path)
    return True

def clean_user_files(port_api : int, uid : int, file_cursor : FileDb):
    rows = file_cursor.clean_sender_files(uid) or []
    for row in rows:
        file_cursor.delete_blob_relations(row[0])
        target_path = file_path(port_api, row[0])
        if os.path.isfile(target_path):
            os.remove(target_path)
    return rows


def release_references(port_api : int, hashes, file_cursor : FileDb,
                       file_last_time : float = 72.0):
    for file_hash in hashes:
        file_cursor.decrement_ref(file_hash)
    return []


def collect_expired(port_api: int, sticker_cursor,  file_cursor: FileDb, file_last_time: float = 0.0):
    """回收过期文件"""
    deleted = []
    for hashes in file_cursor.collect_expired_hashes(file_last_time):
        if sticker_cursor.query_hash_exist(hashes):
            continue
        file_cursor.delete_blob_relations(hashes)
        target_path = file_path(port_api, hashes)
        if os.path.isfile(target_path):
            try:
                os.remove(target_path)
            except OSError:
                continue
        deleted.append(hashes)
    return deleted

def force_delete_file(port_api : int, hashes : str, file_cursor : FileDb):
    file_cursor.force_delete_file(hashes)
    target_path = file_path(port_api, hashes)
    if os.path.isfile(target_path):
        os.remove(target_path)
