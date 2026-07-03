"""
坚守古法编程的 xsfx 太渴望看到 TFV5 finished 的喜悦，没忍住使用 deeepseek 写下了这份测试文件（羞辱）。
应该没人看到吧。
"""


import asyncio
import websockets
import json
import base64
import crypto

pub_pem = crypto.load_pub("res/7001/secret/pub.pem")
aes_key = crypto.generate_aes_key()
uri = 'ws://localhost:11451'

# 用异步队列取代原来的 send_list
send_queue = asyncio.Queue()


def encrypt_response(req: dict):
    json_req = json.dumps(req)
    iv, content = crypto.aes_encrypt(json_req, aes_key)
    iv = base64.b64encode(iv).decode('utf-8')
    content = base64.b64encode(content).decode('utf-8')
    return json.dumps({"iv": iv, "content": content})


def decrypt_response(req: str):
    dict_req = json.loads(req)
    content = crypto.aes_decrypt(
        base64.b64decode(dict_req['iv']),
        base64.b64decode(dict_req['content']),
        aes_key
    )
    return json.loads(content)


uid = input("uid: ")
password = input("password: ")


async def sender(websocket):
    """持续从队列取出请求并加密发送"""
    while True:
        req = await send_queue.get()
        await websocket.send(encrypt_response(req))
        send_queue.task_done()


async def receiver(websocket):
    """持续接收服务器返回并打印"""
    try:
        async for message in websocket:
            print("收到返回的信息 ：", decrypt_response(message))
    except websockets.exceptions.ConnectionClosed:
        print("链接废了")


async def input_handler():
    """将阻塞的 input 放到执行器里，把解析后的 JSON 放入队列"""
    loop = asyncio.get_running_loop()
    while True:
        req_str = await loop.run_in_executor(None, input, "req: ")
        try:
            req = json.loads(req_str)
        except json.JSONDecodeError:
            print("无效 JSON，请重新输入")
            continue
        await send_queue.put(req)


async def test_client():
    async with websockets.connect(uri) as websocket:
        # 1. 发送 AES 密钥
        aes_key_encrypted = crypto.encrypt(pub_pem, aes_key)
        await websocket.send(json.dumps({
            "type": "REQ.UPDATE_AES_KEY",
            "aes_key": base64.b64encode(aes_key_encrypted).decode('utf-8')
        }))

        # 2. 发送登录请求
        await websocket.send(encrypt_response({
            "type": "AUTH.LOGIN",
            "uid": int(uid),
            "password": password
        }))

        # 3. 启动三个并发任务
        tasks = [
            asyncio.create_task(sender(websocket)),
            asyncio.create_task(receiver(websocket)),
            asyncio.create_task(input_handler()),
        ]

        # 等待任何一个任务结束（例如连接断开），然后取消其余任务
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        # 如果有异常可以打印出来
        for task in done:
            if task.exception() is not None:
                print(f"任务异常: {task.exception()}")


if __name__ == "__main__":
    asyncio.run(test_client())