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

def remove_outdate (port_api : int, file_cursor : FileDb): # 删除过期文件
    qry = file_cursor.lose_effect()
    for tmp in qry:
        if os.path.isfile("res/{}/file/{}.file".format(port_api, tmp[3])):
            os.remove("res/{}/file/{}.file".format(port_api, tmp[3]))

def upload_file(port_api : int, uid : int, file_b64 : str, file_name : str, file_cursor : FileDb):
    hashes = sha256(str(time.time()) + str(uid) + file_name)
    with open("res/{}/file/{}.file".format(port_api, hashes), "wb") as file:
        file.write(base64.b64decode(file_b64))
    file_cursor.tag_file(uid, file_name, time.time(), hashes)
    remove_outdate(port_api, file_cursor)
    return hashes


# 实验性新特性：流式分块上传接口，支持超大文件上传。客户端将文件分割成多个块，每次上传一个块，并在最后一个块上传完成后进行文件合并和完整性校验。
def chunked_upload_file(port_api : int, uid : int, file_name : str, chunk_index : int, chunk_total : int, chunk_data_b64 : str, file_id : str = None, file_cursor : FileDb = None, expected_hash : str = None):
    """
    流式分块上传文件（避免大文件内存溢出）
    
    :param port_api: API 端口
    :param uid: 用户 ID
    :param file_name: 文件名
    :param chunk_index: 当前块索引（从 0 开始）
    :param chunk_total: 总块数
    :param chunk_data_b64: 当前块的 Base64 编码数据
    :param file_id: 文件 ID（第一块时为 None，之后返回的值）
    :param file_cursor: 数据库游标（完成时需要）
    :param expected_hash: 客户端计算的文件哈希值（用于完整性校验）
    :return: dict 包含 success/error，以及 file_id（中间块）或 file_hash（最后一块）
    """
    # 单块大小限制（10MB）
    MAX_CHUNK_SIZE = 10 * 1024 * 1024
    if len(chunk_data_b64) > MAX_CHUNK_SIZE:
        return {"success": False, "error": "Chunk too large"}
    
    # 第一块：生成文件 ID
    if chunk_index == 0:
        file_id = sha256(str(time.time()) + str(uid) + file_name)
        temp_path = "res/{}/file/.tmp_{}".format(port_api, file_id)
        try:
            dir_path = os.path.dirname(temp_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        if not file_id:
            return {"success": False, "error": "Missing file_id"}
        temp_path = "res/{}/file/.tmp_{}".format(port_api, file_id)
    
    # 追加写入块数据（二进制模式）
    try:
        decoded_chunk = base64.b64decode(chunk_data_b64)
        with open(temp_path, "ab") as f:
            f.write(decoded_chunk)
    except Exception as e:
        return {"success": False, "error": "Decode or write failed: " + str(e)}
    
    # 最后一块：完成上传，计算最终哈希并移动文件
    if chunk_index == chunk_total - 1:
        try:
            # 计算完整文件的哈希
            with open(temp_path, "rb") as f:
                file_hash = sha256(f.read())
            
            # 哈希校验：如果客户端提供了期望哈希，进行验证
            if expected_hash and file_hash != expected_hash:
                os.remove(temp_path)
                return {
                    "success": False, 
                    "error": "Hash verification failed",
                    "details": f"Expected {expected_hash}, got {file_hash}"
                }
            
            final_path = "res/{}/file/{}.file".format(port_api, file_hash)
            os.rename(temp_path, final_path)
            
            # 数据库记录
            if file_cursor:
                file_cursor.tag_file(uid, file_name, time.time(), file_hash)
                remove_outdate(port_api, file_cursor)
            
            return {"success": True, "file_hash": file_hash, "verified": expected_hash is not None}
        except Exception as e:
            # 清理失败的临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {"success": False, "error": "Finalization failed: " + str(e)}
    
    # 中间块：返回成功和 file_id
    return {"success": True, "file_id": file_id}





# 建议添加一个health check函数，定期检查文件存储目录中的文件是否存在，并删除数据库中对应的记录，以防止无效文件占用服务器空间。