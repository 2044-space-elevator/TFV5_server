import websockets
import time
from argon2 import PasswordHasher
import db
import json
import crypto
import asyncio
import base64

class InstantConnect():
    def __init__(self, port_api, port_tcp, notifiaction_cursor, user_cursor, group_cursor):
        self.port_api = port_api
        self.port_tcp = port_tcp
        self.notification_cursor = notifiaction_cursor
        self.connected_clients = dict()
        self.connected_clients[-1] = []
        self.clients_belonged = dict()
        self.send_queue = dict()
        self.user_cursor = user_cursor
        self.group_cursor = group_cursor
        self.aes_key = dict() 
        self.pri_key = crypto.load_pri("res/{}/secret/pri.pem".format(port_api))
        self.loop = None
    
    def encrypt_response(self, req : dict, websocket):
        json_req = json.dumps(req)
        iv, content = crypto.aes_encrypt(json_req, self.aes_key[websocket])
        iv = base64.b64encode(iv).decode('utf-8')
        content = base64.b64encode(content).decode('utf-8')
        return json.dumps({"iv" : iv, "content" : content}) 

    def _cleanup_client(self, websocket):
        uid = self.clients_belonged.pop(websocket, -1)
        if uid in self.connected_clients and websocket in self.connected_clients[uid]:
            self.connected_clients[uid].remove(websocket)
            if uid != -1 and not self.connected_clients[uid]:
                del self.connected_clients[uid]
        elif websocket in self.connected_clients[-1]:
            self.connected_clients[-1].remove(websocket)
        self.send_queue.pop(websocket, None)
        self.aes_key.pop(websocket, None)

    async def _queue_message(self, websocket, message : dict):
        queue = self.send_queue.get(websocket)
        if queue is not None:
            await queue.put(message)

    async def _disconnect_user(self, uid : int):
        for websocket in list(self.connected_clients.get(uid, [])):
            try:
                await websocket.close()
            except Exception:
                pass
            finally:
                self._cleanup_client(websocket)

    def notify_user(self, uid : int, notification : dict):
        record = {
            "time_stamp" : self.notification_cursor.add_event(uid, notification),
            "info" : notification
        }
        if self.loop is None:
            return record
        for websocket in list(self.connected_clients.get(uid, [])):
            asyncio.run_coroutine_threadsafe(
                self._queue_message(websocket, {"type" : "NOTIFICATION.NEW", "notification" : record}),
                self.loop
            )
        return record

    def disconnect_user(self, uid : int):
        if self.loop is None:
            for websocket in list(self.connected_clients.get(uid, [])):
                self._cleanup_client(websocket)
            return

        asyncio.run_coroutine_threadsafe(self._disconnect_user(uid), self.loop)
    
    async def sender(self, websocket, queue):
        try:
            while True:
                message = await queue.get()
                await websocket.send(self.encrypt_response(message, websocket))
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
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
            self._cleanup_client(websocket)
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
            self.send_queue[websocket] = asyncio.Queue()
            await websocket.send(self.encrypt_response({"type" : "AUTH.LOGIN_SUCCEEDED"}, websocket))

        except Exception as e:
            print("[ERR] 客户端链接 WS 服务器后没有登录")
            self._cleanup_client(websocket)
            return
        
        send_task = asyncio.create_task(self.sender(websocket, self.send_queue[websocket]))

        try:
            async for message in websocket:
                message = json.loads(message)
                message = json.loads(crypto.aes_decrypt(base64.b64decode(message['iv']), base64.b64decode(message['content']), self.aes_key[websocket]))
                if message['type'] == "message.plain":
                    content = message['content']
                    plain = content['plain']
                    send_to = content['send_to']
                    quote = content['quote']
                    if quote < -1:
                        continue
                    send_time = str(time.time())
                    notfic_dict = {
                        "time_stamp" : send_time,
                        "info" : {
                            "event" : "message.plain",
                            "title" : send_time,
                            "content" : plain,
                            "sender" : None,
                            "meta" : quote
                        }
                    }
                    if send_to[0] == 'U':
                        # 发送给用户
                        send_to = int(send_to[1:])
                        notfic_dict["sender"] = "U{}".format(self.clients_belonged[websocket])
                        if self.user_cursor.query_relationship(self.clients_belonged[websocket], send_to):
                            self.notify_user(send_to, notfic_dict)
                            self.notify_user(self.clients_belonged[websocket], notfic_dict)
                            
                    elif send_to[0] == 'G':
                        send_to = int(send_to[1:])
                        members = list(self.group_cursor.query_gid(send_to)[3])
                        notfic_dict["sender"] = "G{}U{}".format(send_to, self.clients_belonged[websocket])
                        if not self.clients_belonged[websocket] in members:
                            continue;
                        for user in members:
                            self.notify_user(user, notfic_dict)
                
                elif message["type"] == "message.file":
                    content = message['content']
                    file_hashes = message['file_hashes']
                    send_to = content['send_to']
                    quote = content['quote']
                    if quote < -1:
                        continue
                    send_time = str(time.time())
                    notfic_dict = {
                        "time_stamp" : send_time,
                        "event" : "message.file",
                        "title" : send_time,
                        "content" : file_hashes,
                        "sender" : None,
                        "meta" : quote
                    }
                    if send_to[0] == 'U':
                        # 发送给用户
                        send_to = int(send_to[1:])
                        notfic_dict["sender"] = "U{}".format(self.clients_belonged[websocket])
                        if self.user_cursor.query_relationship(self.clients_belonged[websocket], send_to):
                            self.notify_user(send_to, notfic_dict)
                            self.notify_user(self.clients_belonged[websocket], notfic_dict)
                            
                    elif send_to[0] == 'G':
                        send_to = int(send_to[1:])
                        members = list(self.group_cursor.query_gid(send_to)[3])
                        notfic_dict["sender"] = "G{}U{}".format(send_to, self.clients_belonged[websocket])
                        if not self.clients_belonged[websocket] in members:
                            continue;
                        for user in members:
                            self.notify_user(user, notfic_dict)

        except Exception:
            pass

        finally:
            send_task.cancel()
            self._cleanup_client(websocket)
            

    async def main(self):
        print("[INFO] 已严肃启动 TCP 服务器")
        self.loop = asyncio.get_running_loop()
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
    group_cursor = db.GroupDb('res/7001/db/group.db', 7001)
    example = InstantConnect(7001, 1145, notification_cursor, user_cursor, group_cursor)
    asyncio.run(example.main())