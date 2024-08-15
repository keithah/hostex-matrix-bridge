import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

class HostexPoller:
    def __init__(self, bridge):
        self.bridge = bridge
        self.poll_interval = 10  # Poll every 60 seconds
        self.time_offset = timedelta(hours=8)  # API time is 8 hours behind local time

    async def start_polling(self):
        self.bridge.log.debug("Starting Hostex polling")
        asyncio.create_task(self.poll_hostex_messages())

    async def poll_hostex_messages(self):
        while True:
            try:
                self.bridge.log.debug("Starting Hostex message poll")
                
                last_poll_time = await self.bridge.database.get_last_poll_time()
                if last_poll_time.tzinfo is None:
                    last_poll_time = last_poll_time.replace(tzinfo=timezone.utc)
                self.bridge.log.debug(f"Last poll time: {last_poll_time}")
                
                conversations = await self.bridge.hostex_api.get_conversations()
                self.bridge.log.debug(f"Retrieved {len(conversations.get('data', {}).get('conversations', []))} conversations")
                
                updated_conversations = []
                for conv in conversations.get('data', {}).get('conversations', []):
                    conv_id = conv['id']
                    conv_last_message_time = self.bridge.hostex_api.parse_timestamp(conv['last_message_at']) + self.time_offset
                    self.bridge.log.debug(f"Conversation {conv_id} last message time: {conv_last_message_time}")
                    if conv_last_message_time > last_poll_time:
                        updated_conversations.append(conv)
                        self.bridge.log.debug(f"Conversation {conv_id} has updates")
                    else:
                        self.bridge.log.debug(f"Conversation {conv_id} has no updates (last message time <= last poll time)")

                self.bridge.log.debug(f"Found {len(updated_conversations)} updated conversations")

                for conv in updated_conversations:
                    conv_id = conv['id']
                    self.bridge.log.debug(f"Processing conversation {conv_id}")
                    
                    messages = await self.bridge.hostex_api.get_conversation_messages(conv_id)
                    self.bridge.log.debug(f"Received {len(messages)} messages for conversation {conv_id}")
                    
                    processed_message_ids = await self.bridge.database.get_processed_message_ids(conv_id)
                    
                    new_messages = [msg for msg in messages if msg['id'] not in processed_message_ids]
                    
                    self.bridge.log.debug(f"Processing {len(new_messages)} new messages for conversation {conv_id}")
                    for message in new_messages:
                        message_time = self.bridge.hostex_api.parse_timestamp(message['created_at']) + self.time_offset
                        self.bridge.log.debug(f"Message {message['id']} time: {message_time}, Last poll time: {last_poll_time}")
                        if message_time > last_poll_time:
                            self.bridge.log.debug(f"Processing message: {message}")
                            await self.bridge.message_handler.process_hostex_message(conv_id, message)
                            await self.bridge.database.add_processed_message_id(conv_id, message['id'])
                        else:
                            self.bridge.log.debug(f"Skipping old message: {message['id']}")

                current_time = datetime.now(timezone.utc)
                self.bridge.log.debug(f"Setting last poll time to {current_time}")
                await self.bridge.database.set_last_poll_time(current_time)
                self.bridge.log.debug(f"Polling complete, sleeping for {self.poll_interval} seconds")
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                self.bridge.log.error(f"Error polling Hostex messages: {e}", exc_info=True)
                self.bridge.log.debug(f"Polling error, sleeping for {self.poll_interval} seconds")
                await asyncio.sleep(self.poll_interval)
