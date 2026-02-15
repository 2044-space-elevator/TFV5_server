import websockets
import time
import asyncio

class NoResponse(Exception):
    """
    5 秒内没回应，移除出 socket 列表
    """
    pass

class InstantConnect():
    def __init__(self, port_tcp, notifiaction_cursor):
        self.port_tcp = port_tcp
        self.connected_clients = dict()
    
    async def handler(self, websocket):
        pass

    async def main(self):
        async with websockets.serve(self.handler, "0.0.0.0", self.port_tcp):
            await asyncio.Future() 