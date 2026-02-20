import websockets
from argon2 import PasswordHasher
import db
import json
import crypto
import time
import asyncio
import base64

class InstantConnect():
    def __init__(self, port_api, port_tcp, notifiaction_cursor, user_cursor):
        self.port_api = port_api
        self.port_tcp = port_tcp
        self.connected_clients = dict()
        self.connected_clients[-1] = []
        self.clients_belonged = dict()
        self.send_queue = dict()
        self.user_cursor = user_cursor
        self.aes_key = dict() 
        self.pri_key = crypto.load_pri("res/{}/secret/pri.pem".format(port_api))
    
    def encrypt_response(self, req : dict, websocket):
        json_req = json.dumps(req)
        iv, content = crypto.aes_encrypt(json_req, self.aes_key[websocket])
        iv = base64.b64encode(iv).decode('utf-8')
        content = base64.b64encode(content).decode('utf-8')
        return json.dumps({"iv" : iv, "content" : content}) 
    
    def send_to_client(self, websocket, message : dict):
        self.send_queue[websocket].put(message)
        notification_cursor.add_event(self.clients_belonged[websocket], message)
    
    async def sender(self, websocket, queue):
        try:
            while True:
                message = await queue.get()
                await websocket.send(self.encrypt_response(message))
        except asyncio.CancelledError:
            pass
    
    async def handler(self, websocket : websockets.ClientConnection):
        self.connected_clients[-1].append(websocket)
        self.clients_belonged[websocket] = -1
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            message = json.loads(message)
            if message['type'] != 'REQ.UPDATE_AES_KEY':
                raise
            message["aes_key"] = base64.b64decode(message["aes_key"])
            self.aes_key[websocket] = crypto.decrypt(self.pri_key, message["aes_key"]) 

        except Exception as e:
            self.connected_clients[-1].remove(websocket)
            del self.clients_belonged[websocket]
            print("[ERR] 客户端链接 WS 服务器后没有发出 AES 密钥声明")
            return
        
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            message = json.loads(message)
            message = json.loads(crypto.aes_decrypt(base64.b64decode(message['iv']), base64.b64decode(message['content']), self.aes_key[websocket]))
            if message['type'] != 'AUTH.LOGIN':
                raise
            if not self.user_cursor.verify_user(message['uid'], message['password']):
                raise
            self.connected_clients[-1].remove(websocket)
            if not message["uid"] in self.connected_clients.keys():
                self.connected_clients[message['uid']] = []
            self.connected_clients[message['uid']].append(websocket)
            self.clients_belonged[websocket] = message['uid']
            await websocket.send(self.encrypt_response({"type" : "AUTH.LOGIN_SUCCEEDED"}, websocket))
            self.send_queue[websocket] = asyncio.Queue()

        except Exception as e:
            print("[ERR] 客户端链接 WS 服务器后没有登录")
            del self.clients_belonged[websocket]
            self.connected_clients[-1].remove(websocket)
            return
        
        send_task = asyncio.create_task(self.sender(websocket, self.send_queue[websocket]))

        try:
            async for message in websocket:
                print("Receive message", message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            send_task.cancel()
            del self.send_queue[websocket]
            

    async def main(self):
        async with websockets.serve(self.handler, "0.0.0.0", self.port_tcp):
            await asyncio.Future() 

if __name__ == '__main__':
    hasher = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=24,
        salt_len=16
    )
    user_cursor = db.UserDb(hasher, 'res/7001/db/user.db', 7001, 1145)
    notification_cursor = db.NotificationsDb('res/7001/db/notification.db', 7001)
    example = InstantConnect(7001, 1145, notification_cursor, user_cursor)
    asyncio.run(example.main())