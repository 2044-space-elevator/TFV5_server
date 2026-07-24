from __future__ import annotations
import os
import base64
import time
from db import FileDb
import hashlib
import mimetypes
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
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
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
                mime_type=mime_type, extension=extension,
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


def release_references(port_api : int, hashes, file_cursor : FileDb,
                       file_last_time : float = 72.0):
    for file_hash in hashes:
        file_cursor.decrement_ref(file_hash)
    deleted = file_cursor.lose_effect(file_last_time)
    for row in deleted:
        target_path = file_path(port_api, row[3])
        if os.path.isfile(target_path):
            os.remove(target_path)
    return deleted

def force_delete_file(port_api : int, hashes : str, file_cursor : FileDb):
    file_cursor.force_delete_file(hashes)
    target_path = file_path(port_api, hashes)
    if os.path.isfile(target_path):
        os.remove(target_path)
