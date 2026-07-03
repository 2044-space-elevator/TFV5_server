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

def upload_file(port_api : int, uid : int, file_b64 : str, file_name : str, file_cursor : FileDb):
    content = base64.b64decode(file_b64)
    hashes = sha256(content)
    existing = file_cursor.return_file(hashes)
    if existing:
        file_cursor.increment_ref(hashes)
    else:
        with open(file_path(port_api, hashes), "wb") as file:
            file.write(content)
        file_cursor.tag_file(uid, file_name, time.time(), hashes)
    qry = file_cursor.lose_effect()
    for tmp in qry:
        tmp_path = file_path(port_api, tmp[3])
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
    return hashes

def dereference_file(port_api : int, hashes : str, file_cursor : FileDb):
    file_cursor.decrement_ref(hashes)
    qry = file_cursor.lose_effect()
    for tmp in qry:
        tmp_path = file_path(port_api, tmp[3])
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)

def clean_user_files(port_api : int, uid : int, file_cursor : FileDb):
    rows = file_cursor.clean_sender_files(uid) or []
    for row in rows:
        target_path = file_path(port_api, row[3])
        if os.path.isfile(target_path):
            os.remove(target_path)
    return rows