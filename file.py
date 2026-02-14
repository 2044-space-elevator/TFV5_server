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
    forum_cursor = FileDb("res/{}/file/file.db".format(port_api), port_api)
    forum_cursor.create_file_db()

def upload_file(port_api : int, uid : int, file_b64 : str, file_name : str, file_cursor : FileDb):
    hashes = sha256(str(time.time()) + str(uid) + file_name)
    with open("res/{}/file/{}.file".format(port_api, hashes), "wb") as file:
        file.write(base64.b64decode(file_b64))
    file_cursor.tag_file(uid, file_name, time.time(), hashes)
    qry = file_cursor.lose_effect()
    for tmp in qry:
        if os.path.isfile("res/{}/file/{}.file".format(port_api, tmp[3])):
            os.remove("res/{}/file/{}.file".format(port_api, tmp[3]))
    return hashes