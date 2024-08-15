from mautrix.types import RoomID, UserID
from datetime import datetime, timezone, timedelta
import logging
from tabulate import tabulate

logger = logging.getLogger(__name__)

class HostexCommands:
    def __init__(self, bridge):
        self.bridge = bridge

    async def handle_admin_command(self, room_id: RoomID, message: str):
        if room_id != self.bridge.admin_room_id:
            await self.bridge.puppet_intent.send_text(room_id, "Admin commands are only available in the admin room.")
            return

        command = message.lower().strip()
        if command == "help":
            await self.send_help(self.bridge.admin_room_id)
        elif command == "status":
            await self.send_status(self.bridge.admin_room_id)
        elif command == "cleanup":
            await self.cleanup_rooms(self.bridge.admin_room_id)
        elif command.startswith("debug"):
            await self.set_debug_mode(self.bridge.admin_room_id, command)
        elif command.startswith("prefix"):
            await self.set_guest_prefix(self.bridge.admin_room_id, command)
        elif command == "force_room_creation":
            await self.force_room_creation(self.bridge.admin_room_id)
        elif command == "force_maintenance":
            await self.force_maintenance(self.bridge.admin_room_id)
        else:
            await self.bridge.puppet_intent.send_text(self.bridge.admin_room_id, "Unknown command. Type 'help' for a list of commands.")

    async def handle_conversation_command(self, room_id: RoomID, message: str):
        command = message.lower().strip()
        if command == "!help":
            await self.send_conversation_help(room_id)
        elif command.startswith("!backfill"):
            await self.backfill_messages(room_id, command)
        elif command == "!messages":
            await self.show_recent_messages(room_id)
        else:
            await self.bridge.puppet_intent.send_text(room_id, "Unknown command. Type '!help' for a list of commands.")

    async def send_help(self, room_id: RoomID):
        help_text = (
            "Available commands:\n"
            "help - Show this help message\n"
            "status - Show bridge status and conversation information\n"
            "cleanup - Remove rooms for conversations older than a week\n"
            "debug on/off - Turn debug mode on or off\n"
            "prefix <new_prefix> - Change the guest name prefix\n"
            "force_room_creation - Force creation of rooms for all conversations\n"
            "force_maintenance - Force maintenance tasks (leave old rooms, ensure user in rooms, load conversations)"
        )
        await self.bridge.puppet_intent.send_text(room_id, help_text)

    async def send_conversation_help(self, room_id: RoomID):
        help_text = (
            "Available commands:\n"
            "!help - Show this help message\n"
            "!backfill [number] - Backfill messages (default: 20, max: 100)\n"
            "!messages - Show recent messages stored in the database"
        )
        await self.bridge.puppet_intent.send_text(room_id, help_text)

    async def send_status(self, room_id: RoomID):
        try:
            status_text = f"Last poll time: {self.bridge.last_poll_time or 'Never'}\n\n"
            
            table_data = []
            conversations = await self.bridge.update_conversations()
            for conv in conversations:
                name = conv.get('guest', {}).get('name', 'Unknown')
                phone = conv.get('guest', {}).get('phone', '')
                last_activity = conv.get('last_message_at', 'Unknown')
                conversation_id = conv.get('id', 'Unknown')
                room_id_info = self.bridge.conversation_rooms.get(conversation_id, {}).get('room_id', 'Not bridged')

                if isinstance(phone, str) and len(phone) > 4:
                    phone = f"...{phone[-4:]}"
                else:
                    phone = "N/A"

                table_data.append([name, phone, last_activity, room_id_info])

            table_data.sort(key=lambda x: x[2], reverse=True)  # Sort by last activity, most recent first
            
            table_headers = ["Name", "Last 4 of Phone", "Last Activity", "Room ID"]
            status_text += tabulate(table_data, headers=table_headers, tablefmt="grid")
            
            await self.bridge.puppet_intent.send_text(self.bridge.admin_room_id, status_text)
        except Exception as e:
            logger.error(f"Error sending status message: {e}", exc_info=True)

    async def cleanup_rooms(self, room_id: RoomID):
        removed_rooms = 0
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        for conv_id, room_data in list(self.bridge.conversation_rooms.items()):
            last_message_time = room_data.get('last_message_time')
            if last_message_time:
                if last_message_time.tzinfo is None:
                    last_message_time = last_message_time.replace(tzinfo=timezone.utc)
                
                if last_message_time < one_week_ago:
                    try:
                        # Check if the user is in the room before trying to leave
                        members = await self.bridge.puppet_intent.get_joined_members(room_data['room_id'])
                        if self.bridge.user_id in members:
                            await self.bridge.puppet_intent.leave_room(room_data['room_id'])
                        del self.bridge.conversation_rooms[conv_id]
                        removed_rooms += 1
                    except Exception as e:
                        logger.error(f"Error processing room {room_data['room_id']} for conversation {conv_id}: {e}")
        
        await self.bridge.database.save_room_states(self.bridge.conversation_rooms)
        
        cleanup_message = f"Cleanup complete. Removed {removed_rooms} room(s)."
        await self.bridge.puppet_intent.send_text(room_id, cleanup_message)

    async def set_debug_mode(self, room_id: RoomID, command: str):
        self.bridge.debug = command.endswith("on")
        await self.bridge.puppet_intent.send_text(room_id, f"Debug mode: {'on' if self.bridge.debug else 'off'}")

    async def set_guest_prefix(self, room_id: RoomID, command: str):
        new_prefix = command.split(maxsplit=1)[1] if len(command.split()) > 1 else ""
        if new_prefix:
            self.bridge.guest_prefix = new_prefix
            await self.bridge.puppet_intent.send_text(room_id, f"Guest name prefix changed to: {self.bridge.guest_prefix}")
            await self.update_room_names()
        else:
            await self.bridge.puppet_intent.send_text(room_id, f"Current guest name prefix: {self.bridge.guest_prefix}")

    async def update_room_names(self):
        for conv_id, room_data in self.bridge.conversation_rooms.items():
            conv = next((c for c in self.bridge.all_conversations if c.get('id') == conv_id), None)
            if conv:
                room_name = f"{self.bridge.guest_prefix} {conv.get('guest', {}).get('name', 'Unknown')}"
                await self.bridge.puppet_intent.set_room_name(room_data['room_id'], room_name)

    async def backfill_messages(self, room_id: RoomID, command: str):
        parts = command.split()
        limit = 20
        if len(parts) > 1:
            try:
                limit = int(parts[1])
                limit = min(max(1, limit), 100)
            except ValueError:
                await self.bridge.puppet_intent.send_text(room_id, "Invalid number. Using default of 20 messages.")

        conversation_id = next((conv_id for conv_id, data in self.bridge.conversation_rooms.items() if data['room_id'] == room_id), None)
        if conversation_id:
            messages = await self.bridge.hostex_api.get_conversation_messages(conversation_id, limit)
            messages.sort(key=lambda x: x['created_at'])  # Sort oldest to newest
            for message in messages:
                await self.bridge.message_handler.process_hostex_message(conversation_id, message)
            await self.bridge.puppet_intent.send_text(room_id, f"Backfilled {len(messages)} messages.")
        else:
            await self.bridge.puppet_intent.send_text(room_id, "This room is not associated with a Hostex conversation.")

    async def show_recent_messages(self, room_id: RoomID):
        conversation_id = next((conv_id for conv_id, data in self.bridge.conversation_rooms.items() if data['room_id'] == room_id), None)
        if conversation_id:
            messages = await self.bridge.database.get_recent_messages(conversation_id, limit=100)
            if messages:
                table_data = [
                    (
                        msg['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                        msg['id'],
                        "Received" if msg['sender_role'] == 'guest' else "Sent",
                        msg['content'][:200] + ('...' if len(msg['content']) > 200 else '')
                    )
                    for msg in messages
                ]
                table_data.sort(key=lambda x: x[0])  # Sort by timestamp (oldest to newest)
                table = tabulate(table_data, headers=['Date', 'ID', 'Direction', 'Content'], tablefmt='grid')
                await self.bridge.puppet_intent.send_text(room_id, f"Recent messages:\n```\n{table}\n```")
            else:
                await self.bridge.puppet_intent.send_text(room_id, "No recent messages found.")
        else:
            await self.bridge.puppet_intent.send_text(room_id, "This room is not associated with a Hostex conversation.")

    async def force_room_creation(self, room_id: RoomID):
        await self.bridge.puppet_intent.send_text(room_id, "Forcing room creation for all conversations...")
        conversations = await self.bridge.hostex_api.get_conversations()
        for conv in conversations.get('data', {}).get('conversations', []):
            conv_id = conv['id']
            guest_name = conv['guest']['name']
            if conv_id not in self.bridge.conversation_rooms:
                try:
                    new_room_id, created = await self.bridge.room_manager.create_conversation_room(conv_id, guest_name)
                    if created:
                        await self.bridge.puppet_intent.send_text(room_id, f"Created room for conversation {conv_id} with guest {guest_name}: {new_room_id}")
                    else:
                        await self.bridge.puppet_intent.send_text(room_id, f"Room already exists for conversation {conv_id} with guest {guest_name}: {new_room_id}")
                except Exception as e:
                    await self.bridge.puppet_intent.send_text(room_id, f"Error creating room for conversation {conv_id}: {str(e)}")
        await self.bridge.puppet_intent.send_text(room_id, "Forced room creation complete.")

    async def force_maintenance(self, room_id: RoomID):
        await self.bridge.puppet_intent.send_text(room_id, "Forcing maintenance tasks...")
        await self.bridge.force_maintenance()
        await self.bridge.puppet_intent.send_text(room_id, "Maintenance tasks completed.")
