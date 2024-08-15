from mautrix.types import MessageEvent, MessageType, RoomID, TextMessageEventContent, EventType
from datetime import datetime, timezone
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

class HostexMessageHandler:
    def __init__(self, bridge):
        self.bridge = bridge
        self.processed_events = set()
        self.matrix_sent_messages = {}  # {room_id: {message_content: timestamp}}
        self.message_expiry_time = 300  # 5 minutes

    async def handle_matrix_event(self, event):
        self.bridge.log.debug(f"Received event: {event}")
        
        if event.event_id in self.processed_events:
            self.bridge.log.debug(f"Skipping already processed event: {event.event_id}")
            return
        
        self.processed_events.add(event.event_id)
        if len(self.processed_events) > 1000:
            self.processed_events.pop()

        if isinstance(event, MessageEvent) and event.content.msgtype == MessageType.TEXT:
            self.bridge.log.debug(f"Received text message in room {event.room_id} from {event.sender}: {event.content.body}")
            
            if event.room_id == self.bridge.admin_room_id:
                self.bridge.log.debug(f"Handling admin command: {event.content.body}")
                await self.bridge.commands.handle_admin_command(event.room_id, event.content.body)
            elif event.sender != self.bridge.puppet_mxid:
                # Handle messages from any user in the room except our puppet
                await self.send_hostex_message(event.room_id, event.content.body, event.sender)
        else:
            self.bridge.log.debug(f"Received non-text event: {event}")

    async def process_hostex_message(self, conversation_id: str, message: dict):
        self.bridge.log.debug(f"Processing Hostex message: {message}")
        
        room_data = self.bridge.conversation_rooms.get(conversation_id)
        if not room_data:
            self.bridge.log.error(f"No room found for conversation {conversation_id}")
            return
        room_id = room_data['room_id']

        content = message.get('content', '')
        timestamp_str = message.get('created_at')
        
        # Check if this message was recently sent from Matrix
        if room_id in self.matrix_sent_messages and content in self.matrix_sent_messages[room_id]:
            self.bridge.log.debug(f"Skipping echo of message sent from Matrix: {content}")
            return

        message_content = TextMessageEventContent(
            msgtype=MessageType.TEXT,
            body=content,
        )

        try:
            timestamp = self.bridge.hostex_api.parse_timestamp(timestamp_str)
            timestamp_ms = int(timestamp.timestamp() * 1000)
            
            self.bridge.log.debug(f"Attempting to send message to room {room_id}: {content}")
            
            # Ensure the puppet is in the room
            try:
                await self.bridge.room_manager.ensure_puppet_in_room(room_id)
            except Exception as e:
                self.bridge.log.error(f"Failed to ensure puppet in room {room_id}: {e}")
                return

            event_id = await self.bridge.puppet_intent.send_message(room_id, message_content, timestamp=timestamp_ms)
            
            self.bridge.log.info(f"Successfully sent message to room {room_id}. Event ID: {event_id}")
        
            self.bridge.conversation_rooms[conversation_id]['last_message'] = content
            self.bridge.conversation_rooms[conversation_id]['last_message_time'] = timestamp
        except Exception as e:
            self.bridge.log.error(f"Failed to process message for room {room_id}: {e}", exc_info=True)

    async def send_hostex_message(self, room_id: RoomID, message: str, sender: str):
        conversation_id = next((conv_id for conv_id, data in self.bridge.conversation_rooms.items() if data['room_id'] == room_id), None)
        if conversation_id:
            try:
                self.bridge.log.debug(f"Attempting to send message to Hostex: {message}")
                response = await self.bridge.hostex_api.send_message(conversation_id, message)
                self.bridge.log.debug(f"Hostex API response: {response}")
                
                if response.get('error_code') == 200:
                    self.bridge.log.info(f"Message sent successfully to Hostex: {message}")
                    # Record this message as sent from Matrix
                    if room_id not in self.matrix_sent_messages:
                        self.matrix_sent_messages[room_id] = {}
                    self.matrix_sent_messages[room_id][message] = time.time()
                else:
                    self.bridge.log.error(f"Failed to send message to Hostex. Error: {response.get('error_msg')}")
            except Exception as e:
                self.bridge.log.error(f"Exception when sending message to Hostex: {e}", exc_info=True)
        else:
            self.bridge.log.error(f"No conversation found for room {room_id}")
            await self.bridge.puppet_intent.send_notice(room_id, "This room is not associated with a Hostex conversation.")

    def clean_old_messages(self):
        current_time = time.time()
        for room_id in list(self.matrix_sent_messages.keys()):
            self.matrix_sent_messages[room_id] = {
                content: timestamp
                for content, timestamp in self.matrix_sent_messages[room_id].items()
                if current_time - timestamp <= self.message_expiry_time
            }
            if not self.matrix_sent_messages[room_id]:
                del self.matrix_sent_messages[room_id]

    async def backfill_messages(self, conversation_id: str, room_id: RoomID):
        messages = await self.bridge.hostex_api.get_conversation_messages(conversation_id, 5)
        for message in reversed(messages):
            await self.process_hostex_message(conversation_id, message)
