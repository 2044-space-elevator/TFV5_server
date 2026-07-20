from __future__ import annotations
import os
import base64
import time
from db import FileDb
import hashlib

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

    already_owned = file_cursor.has_active_user_file(uid, hashes)

    if file_cursor.file_exists(hashes):
        if not already_owned:
            file_cursor.increment_ref(hashes)
            file_cursor.increment_upload_user_count(hashes)
    else:
        disk_path = file_path(port_api, hashes)
        try:
            with open(disk_path, "wb") as file:
                file.write(content)
        except Exception:
            raise
        try:
            # 并发修复
            file_cursor.tag_file(uid, file_name, time.time(), hashes, file_size)
        except Exception:
            if os.path.isfile(disk_path):
                os.remove(disk_path)
            raise

    try:
        file_cursor.add_user_file(uid, hashes, file_name, time.time())
    except Exception:
        if not already_owned and file_cursor.file_exists(hashes):
            file_cursor.decrement_ref(hashes)
        raise

    qry = file_cursor.lose_effect(file_last_time)
    for tmp in qry:
        tmp_path = file_path(port_api, tmp[3])
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
    return hashes

def dereference_file(port_api : int, uid : int, hashes : str, file_cursor : FileDb, file_last_time : float = 72.0):
    if not file_cursor.decrement_owned_ref(uid, hashes):
        return False
    qry = file_cursor.lose_effect(file_last_time)
    for tmp in qry:
        tmp_path = file_path(port_api, tmp[3])
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
    return True

def delete_user_file(port_api : int, uid : int, hashes : str, file_cursor : FileDb):
    succeeded, deleted = file_cursor.delete_owned_user_file(uid, hashes)
    if not succeeded:
        return False
    for row in deleted:
        tmp_path = file_path(port_api, row[3])
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
    return True

def clean_user_files(port_api : int, uid : int, file_cursor : FileDb):
    rows = file_cursor.clean_sender_files(uid) or []
    for row in rows:
        target_path = file_path(port_api, row[3])
        if os.path.isfile(target_path):
            os.remove(target_path)
    return rows

def force_delete_file(port_api : int, hashes : str, file_cursor : FileDb):
    file_cursor.force_delete_file(hashes)
    target_path = file_path(port_api, hashes)
    if os.path.isfile(target_path):
        os.remove(target_path)
