import asyncio
import aiohttp
import json
import logging
from mautrix.types import Event

logger = logging.getLogger(__name__)

class AppserviceWebsocket:
    def __init__(self, url, token, callback):
        self.url = url + "/_matrix/client/unstable/fi.mau.as_sync"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Mautrix-Websocket-Version": "3",
        }
        self.callback = callback

    async def start(self):
        asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            try:
                logger.info(f"Connecting to {self.url}...")

                async with aiohttp.ClientSession(headers=self.headers) as sess:
                    async with sess.ws_connect(self.url) as ws:
                        logger.info("Websocket connected.")

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                logger.debug(f"Received websocket message: {msg.data}")
                                data = msg.json()
                                if data["status"] == "ok" and data["command"] == "transaction":
                                    logger.debug(f"Websocket transaction {data['txn_id']}")
                                    for event in data["events"]:
                                        try:
                                            logger.debug(f"Processing event: {event}")
                                            await self.callback(Event.deserialize(event))
                                        except Exception as e:
                                            logger.error(f"Error processing event: {e}", exc_info=True)

                                    await ws.send_str(
                                        json.dumps(
                                            {
                                                "command": "response",
                                                "id": data["id"],
                                                "data": {},
                                            }
                                        )
                                    )
                                else:
                                    logger.warn("Unhandled WS command: %s", data)
                            else:
                                logger.debug(f"Unhandled WS message type: {msg.type}")

                logger.info("Websocket disconnected.")
            except asyncio.CancelledError:
                logger.info("Websocket was cancelled.")
                return
            except Exception as e:
                logger.error(f"Websocket error: {e}", exc_info=True)

                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    return
