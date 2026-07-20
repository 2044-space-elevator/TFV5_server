import websockets
import time
from argon2 import PasswordHasher
import db
import json
import crypto
import asyncio
import base64
import os
import threading
from collections import defaultdict


def can_access_room(user_cursor, group_cursor, uid: int, room_id: str) -> bool:
    if not isinstance(room_id, str) or len(room_id) < 2:
        return False
    try:
        target_id = int(room_id[1:])
    except (TypeError, ValueError):
        return False
    if room_id.startswith('U'):
        return user_cursor.is_friend(uid, target_id)
    if room_id.startswith('G'):
        return group_cursor.is_member(target_id, uid)
    return False

class InstantConnect():
    def __init__(self, port_api, port_tcp, notification_cursor, user_cursor, messages_cursor, group_cursor):
        self.port_api = port_api
        self.port_tcp = port_tcp
        self.notification_cursor = notification_cursor
        self.connected_clients = dict()
        self.connected_clients[-1] = []
        self.clients_belonged = dict()
        self.send_queue = dict()
        self.user_cursor = user_cursor
        self.group_cursor = group_cursor
        self.messages_cursor = messages_cursor
        self._load_config()
        self.aes_key = dict()
        self.pri_key = crypto.load_pri("res/{}/secret/pri.pem".format(port_api))
        self.loop = None
        self._ws_lock = threading.Lock()
        self._ws_timestamps = defaultdict(list)
        self._ws_typing_timestamps = defaultdict(list)
        self._clients_lock = threading.Lock()

    def _check_ws_rate(self, uid: int, max_per_second: int = 10, bucket: str = "msg") -> bool:
        now = time.time()
        ts_dict = self._ws_typing_timestamps if bucket == "typing" else self._ws_timestamps
        with self._ws_lock:
            cutoff = now - 1.0
            ts_dict[uid] = [t for t in ts_dict[uid] if t > cutoff]
            if len(ts_dict[uid]) >= max_per_second:
                return False
            ts_dict[uid].append(now)
            return True

    def _load_config(self):
        cfg_path = os.path.join("res", str(self.port_api), "config.json")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.max_message_length = cfg.get("max_message_length", 10000)
        except Exception:
            self.max_message_length = 10000
    
    def encrypt_response(self, req : dict, websocket):
        json_req = json.dumps(req)
        iv, content = crypto.aes_encrypt(json_req, self.aes_key[websocket])
        iv = base64.b64encode(iv).decode('utf-8')
        content = base64.b64encode(content).decode('utf-8')
        return json.dumps({"iv" : iv, "content" : content}) 

    def _verify_quote(self, quote_mid: int, send_to: str, sender_uid: int) -> bool:
        rows = self.messages_cursor.query(
            "SELECT sender_uid, receiver_uid, group_id, deleted FROM messages WHERE mid = ?",
            (quote_mid,)
        )
        if not rows:
            return False
        r = rows[0]
        if r[3]:  # deleted
            return False
        if send_to[0] == 'G':
            gid = int(send_to[1:])
            if r[2] != gid:
                return False
            return self.group_cursor.is_member(gid, sender_uid)
        else:
            target_uid = int(send_to[1:])
            return (r[0] == sender_uid and r[1] == target_uid) or \
                   (r[0] == target_uid and r[1] == sender_uid)

    def _cleanup_client(self, websocket):
        with self._clients_lock:
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

    async def _notify_user_async(self, uid : int, notification : dict):
        return await asyncio.to_thread(self.notify_user, uid, notification)

    def _queue_ack(self, websocket, client_mid=None, status="sent", mid=None, error=None):
        if client_mid is None or websocket not in self.send_queue or self.loop is None:
            return
        ack = {"type": "message.ack", "client_mid": client_mid, "status": status}
        if mid is not None:
            ack["mid"] = mid
        if error is not None:
            ack["error"] = error
        asyncio.run_coroutine_threadsafe(self.send_queue[websocket].put(ack), self.loop)

    async def _disconnect_user(self, uid : int):
        with self._clients_lock:
            clients = list(self.connected_clients.get(uid, []))
        for websocket in clients:
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
        with self._clients_lock:
            clients = list(self.connected_clients.get(uid, []))
        for websocket in clients:
            asyncio.run_coroutine_threadsafe(
                self._queue_message(websocket, {"type" : "NOTIFICATION.NEW", "notification" : record}),
                self.loop
            )
        return record

    def disconnect_user(self, uid : int):
        if self.loop is None:
            with self._clients_lock:
                clients = list(self.connected_clients.get(uid, []))
            for websocket in clients:
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
    
    async def handler(self, websocket : websockets.WebSocketServerProtocol):
        with self._clients_lock:
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
            with self._clients_lock:
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
                sender_uid = self.clients_belonged[websocket]

                if message['type'] == 'PING':
                    await self._queue_message(websocket, {"type": "PONG"})
                    continue

                if message['type'] in ("message.plain", "message.file"):
                    info = self.user_cursor.uid_query(sender_uid)
                    if not info or info[0][4] == 'banned':
                        self._queue_ack(websocket, message.get('client_mid'), status="failed", error="banned")
                        break

                    if not self._check_ws_rate(sender_uid):
                        self._queue_ack(websocket, message.get('client_mid'), status="failed", error="rate_limited")
                        continue
                if message['type'] == "message.plain":
                    content = message['content']
                    plain = content['plain']
                    send_to = content['send_to']
                    quote = content['quote']
                    client_mid = message.get('client_mid')
                    if quote < -1:
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_quote")
                        continue
                    if quote >= 0 and not self._verify_quote(quote, send_to, self.clients_belonged[websocket]):
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_quote")
                        continue
                    if len(plain) > self.max_message_length:
                        self._queue_ack(websocket, client_mid, status="failed", error="message_too_long")
                        continue
                    if send_to[0] == 'U':
                        # 发送给用户
                        send_to = int(send_to[1:])
                        sender_uid = self.clients_belonged[websocket]
                        if not self.user_cursor.is_friend(sender_uid, send_to):
                            self._queue_ack(websocket, client_mid, status="failed", error="not_friends")
                            continue
                        msg_record = self.messages_cursor.add_message(
                            sender_uid, send_to, plain,
                            content_type='plain', quote=quote,
                            client_mid=client_mid
                        )
                        self._queue_ack(websocket, client_mid, mid=msg_record["mid"], status="sent")
                        if msg_record.get("duplicate"):
                            continue
                        sender_str = "U{}".format(sender_uid)
                        recv_notif = {
                            "event" : "message.plain",
                            "title" : str(msg_record["send_time"]),
                            "content" : plain,
                            "sender" : sender_str,
                            "meta" : quote,
                            "mid" : msg_record["mid"],
                            "client_mid" : client_mid,
                            "room_id" : sender_str
                        }
                        sender_notif = dict(recv_notif)
                        sender_notif["room_id"] = "U{}".format(send_to)
                        await self._notify_user_async(send_to, recv_notif)
                        await self._notify_user_async(sender_uid, sender_notif)

                    elif send_to[0] == 'G':
                        gid = int(send_to[1:])
                        group = self.group_cursor.query_gid(gid)
                        if not group:
                            self._queue_ack(websocket, client_mid, status="failed", error="group_not_found")
                            continue
                        members = self.group_cursor.get_member_uids(gid)
                        sender_str = "G{}U{}".format(gid, self.clients_belonged[websocket])
                        if not self.clients_belonged[websocket] in members:
                            self._queue_ack(websocket, client_mid, status="failed", error="not_group_member")
                            continue
                        msg_record = self.messages_cursor.add_message(
                            self.clients_belonged[websocket], 0, plain,
                            content_type='plain', quote=quote, group_id=gid,
                            client_mid=client_mid
                        )
                        self._queue_ack(websocket, client_mid, mid=msg_record["mid"], status="sent")
                        if msg_record.get("duplicate"):
                            continue
                        notif_dict = {
                            "event" : "message.plain",
                            "title" : str(msg_record["send_time"]),
                            "content" : plain,
                            "sender" : sender_str,
                            "meta" : quote,
                            "mid" : msg_record["mid"],
                            "client_mid" : client_mid,
                            "room_id" : "G{}".format(gid),
                            "group_id" : gid
                        }
                        for user in members:
                            await self._notify_user_async(user, notif_dict)

                    else:
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_target")

                elif message["type"] == "message.file":
                    content = message['content']
                    file_hashes = content['file_hashes']
                    send_to = content['send_to']
                    quote = content['quote']
                    client_mid = message.get('client_mid')
                    if quote < -1:
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_quote")
                        continue
                    if quote >= 0 and not self._verify_quote(quote, send_to, self.clients_belonged[websocket]):
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_quote")
                        continue
                    # hyw
                    if not isinstance(file_hashes, str) or len(file_hashes) != 64 or not all(c in '0123456789abcdefABCDEF' for c in file_hashes):
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_file_hash")
                        continue
                    if send_to[0] == 'U':
                        # 发送给用户
                        send_to = int(send_to[1:])
                        sender_uid = self.clients_belonged[websocket]
                        if not self.user_cursor.is_friend(sender_uid, send_to):
                            self._queue_ack(websocket, client_mid, status="failed", error="not_friends")
                            continue
                        msg_record = self.messages_cursor.add_message(
                            sender_uid, send_to, file_hashes,
                            content_type='file', file_hash=file_hashes, quote=quote,
                            client_mid=client_mid
                        )
                        self._queue_ack(websocket, client_mid, mid=msg_record["mid"], status="sent")
                        if msg_record.get("duplicate"):
                            continue
                        sender_str = "U{}".format(sender_uid)
                        recv_notif = {
                            "event" : "message.file",
                            "title" : str(msg_record["send_time"]),
                            "content" : file_hashes,
                            "sender" : sender_str,
                            "meta" : quote,
                            "mid" : msg_record["mid"],
                            "file_hash" : file_hashes,
                            "client_mid" : client_mid,
                            "room_id" : sender_str
                        }
                        sender_notif = dict(recv_notif)
                        sender_notif["room_id"] = "U{}".format(send_to)
                        await self._notify_user_async(send_to, recv_notif)
                        await self._notify_user_async(sender_uid, sender_notif)

                    elif send_to[0] == 'G':
                        gid = int(send_to[1:])
                        group = self.group_cursor.query_gid(gid)
                        if not group:
                            self._queue_ack(websocket, client_mid, status="failed", error="group_not_found")
                            continue
                        members = self.group_cursor.get_member_uids(gid)
                        sender_str = "G{}U{}".format(gid, self.clients_belonged[websocket])
                        if not self.clients_belonged[websocket] in members:
                            self._queue_ack(websocket, client_mid, status="failed", error="not_group_member")
                            continue
                        msg_record = self.messages_cursor.add_message(
                            self.clients_belonged[websocket], 0, file_hashes,
                            content_type='file', file_hash=file_hashes, quote=quote, group_id=gid,
                            client_mid=client_mid
                        )
                        self._queue_ack(websocket, client_mid, mid=msg_record["mid"], status="sent")
                        if msg_record.get("duplicate"):
                            continue
                        notif_dict = {
                            "event" : "message.file",
                            "title" : str(msg_record["send_time"]),
                            "content" : file_hashes,
                            "sender" : sender_str,
                            "meta" : quote,
                            "mid" : msg_record["mid"],
                            "file_hash" : file_hashes,
                            "client_mid" : client_mid,
                            "room_id" : "G{}".format(gid),
                            "group_id" : gid
                        }
                        for user in members:
                            await self._notify_user_async(user, notif_dict)

                    else:
                        self._queue_ack(websocket, client_mid, status="failed", error="invalid_target")

                elif message["type"] in ("typing.start", "typing.stop"):
                    if not self._check_ws_rate(sender_uid, max_per_second=20, bucket="typing"):
                        continue
                    room_id = message["room_id"]
                    sender_uid = self.clients_belonged[websocket]
                    if not can_access_room(self.user_cursor, self.group_cursor, sender_uid, room_id):
                        continue
                    broadcast = {
                        "type": message["type"],
                        "room_id": room_id,
                        "uid": sender_uid,
                    }
                    if room_id.startswith('U'):
                        target = int(room_id[1:])
                        with self._clients_lock:
                            clients = list(self.connected_clients.get(target, []))
                        for ws in clients:
                            asyncio.run_coroutine_threadsafe(
                                self._queue_message(ws, broadcast), self.loop)
                    elif room_id.startswith('G'):
                        gid = int(room_id[1:])
                        members = self.group_cursor.get_member_uids(gid)
                        for user in members:
                            if user != sender_uid:
                                with self._clients_lock:
                                    clients = list(self.connected_clients.get(user, []))
                                for ws in clients:
                                    asyncio.run_coroutine_threadsafe(
                                        self._queue_message(ws, broadcast), self.loop)

        except Exception as e:
            print("[ERR] WS消息处理异常: {}".format(e))

        finally:
            send_task.cancel()
            self._cleanup_client(websocket)
            

    async def main(self):
        print("[INFO] 已严肃启动 TCP 服务器")
        self.loop = asyncio.get_running_loop()
        async with websockets.serve(self.handler, "0.0.0.0", self.port_tcp):
            await asyncio.Future() 

