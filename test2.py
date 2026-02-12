import base64
import requests
from crypto import *

resquest_body = input("输入想测试的请求体（要求 JSON 格式）")
pub_path = "res/7001/secret/pub.pem"
pub = load_pub(pub_path)
# 生成 AES 密钥
aes_key = generate_aes_key()
# RSA 加密 AES 密钥
aes_key_cry = encrypt(pub, aes_key)
# AES 加密请求体
iv, req_body_cry = aes_encrypt(resquest_body, aes_key)
# IV，加密后的 AES 密钥，加密后的请求体的 Base64 编码
aes_key_cry = base64.b64encode(aes_key_cry).decode('utf-8')
iv = base64.b64encode(iv).decode('utf-8')
req_body_cry = base64.b64encode(req_body_cry).decode('utf-8')

# 发过去的请求体
req = dict()
req["key"] = aes_key_cry
req["iv"] = iv
req["content"] = req_body_cry

print("这是发过去的请求体：", req)
url = "http://127.0.0.1:7001/forum/remove_comment"
resp = requests.post(url, json=req)
print(resp)

# 返回体转为 dict
try:
    resp_t = json.loads(resp.content)
    if resp_t == {}:
        raise
except:
    print("failed")

# 获取返回体密文和 iv
ret = resp_t["content"]
ret_iv = resp_t["iv"]
ret = base64.b64decode(ret)
ret_iv = base64.b64decode(ret_iv)
print(aes_decrypt(ret_iv, ret, aes_key).decode("utf-8"))