import crypto
import asyncio
import threading 
import websockets
import json
import base64

pub_pem = crypto.load_pub("res/7001/secret/pub.pem")
aes_key = crypto.generate_aes_key()
uri = 'ws://localhost:1145'
def encrypt_response(req : dict):
    json_req = json.dumps(req)
    iv, content = crypto.aes_encrypt(json_req, aes_key)
    iv = base64.b64encode(iv).decode('utf-8')
    content = base64.b64encode(content).decode('utf-8')
    return json.dumps({"iv" : iv, "content" : content})

def decrypt_response(req : str):
    dict_req = json.loads(req)
    content = crypto.aes_decrypt(base64.b64decode(dict_req['iv']), base64.b64decode(dict_req['content']), aes_key)
    return json.loads(content)

send_list = []
uid = input("uid:")
password = input("password:")
async def test_client():
    async with websockets.connect(uri) as websocket:
        try:
            aes_key_encrypted = crypto.encrypt(pub_pem, aes_key)
            await websocket.send(json.dumps({
                "type" : "REQ.UPDATE_AES_KEY",
                "aes_key" : base64.b64encode(aes_key_encrypted).decode('utf-8')
            }))
            await websocket.send(encrypt_response(
                {"type" : "AUTH.LOGIN", "uid" : int(uid), "password" : password}
            ))
            for i in send_list:
                await websocket.send(encrypt_response(i))
                send_list.remove(i)
            response = await websocket.recv()
            print("收到返回的信息 ：", decrypt_response(response))
        except websockets.exceptions.ConnectionClosed:
            print("链接废了")

def input_resp():
    req = input("req:")
    req = json.loads(req)
    send_list.append(req)

thread = threading.Thread(target=input_resp)
asyncio.run(test_client())
thread.start()