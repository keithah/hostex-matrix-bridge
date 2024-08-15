from mautrix.types import RoomID, RoomCreatePreset, EventType
from datetime import datetime, timezone, timedelta
import logging
from mautrix.errors import MForbidden

logger = logging.getLogger(__name__)

class HostexRoomManager:
    def __init__(self, bridge):
        self.bridge = bridge

    async def load_room_states(self):
        rows = await self.bridge.database.load_room_states()
        for row in rows:
            if row['conversation_id'] == "admin_room":
                self.bridge.admin_room_id = RoomID(row['room_id'])
            else:
                self.bridge.conversation_rooms[row['conversation_id']] = {
                    'room_id': RoomID(row['room_id']),
                    'last_message': row.get('last_message'),
                    'last_message_time': row.get('last_message_time')
                }

    async def ensure_admin_room(self):
        if not self.bridge.admin_room_id:
            try:
                self.bridge.admin_room_id = await self.bridge.puppet_intent.create_room(
                    name="Hostex Admin",
                    is_direct=True,
                    preset=RoomCreatePreset.PRIVATE,
                )
                await self.bridge.database.save_room_states({"admin_room": {"room_id": self.bridge.admin_room_id}})
            except Exception as e:
                logger.error(f"Failed to create admin room: {str(e)}", exc_info=True)
                return

        if self.bridge.admin_room_id:
            await self.bridge.puppet_intent.send_text(self.bridge.admin_room_id, "Bridge is online, type 'help' for a list of commands.")
            
    async def load_conversations(self):
        response = await self.bridge.hostex_api.get_conversations()
        self.bridge.all_conversations = response.get('data', {}).get('conversations', [])
        self.bridge.all_conversations.sort(key=lambda x: x['last_message_at'])

        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        for conv in self.bridge.all_conversations:
            conv_id = conv['id']
            last_message_at = datetime.fromisoformat(conv['last_message_at'].rstrip('Z')).replace(tzinfo=timezone.utc)

            if last_message_at > one_week_ago:
                if conv_id not in self.bridge.conversation_rooms:
                    room_id, created = await self.create_conversation_room(conv_id, conv['guest']['name'])
                    if room_id:
                        self.bridge.conversation_rooms[conv_id] = {
                            'room_id': room_id,
                            'last_message': None,
                            'last_message_time': last_message_at
                        }
                        if created:
                            await self.bridge.message_handler.backfill_messages(conv_id, room_id)
            elif conv_id in self.bridge.conversation_rooms:
                del self.bridge.conversation_rooms[conv_id]

        await self.bridge.database.save_room_states(self.bridge.conversation_rooms)

    async def create_conversation_room(self, conversation_id: str, guest_name: str):
        existing_room = self.bridge.conversation_rooms.get(conversation_id, {}).get('room_id')
        if existing_room:
            self.bridge.log.debug(f"Room already exists for conversation {conversation_id}: {existing_room}")
            return existing_room, False

        room_name = f"{self.bridge.guest_prefix} {guest_name}"
        try:
            self.bridge.log.debug(f"Creating room for conversation {conversation_id} with name {room_name}")
            room_id = await self.bridge.puppet_intent.create_room(
                name=room_name,
                is_direct=True,
                preset=RoomCreatePreset.PRIVATE,
            )
            self.bridge.log.info(f"Created room for conversation {conversation_id}: {room_id}")
            
            # Ensure the puppet is in the room
            await self.ensure_puppet_in_room(room_id)
            
            # Invite the user to the room
            try:
                await self.bridge.puppet_intent.invite_user(room_id, self.bridge.user_id)
                self.bridge.log.info(f"Invited user {self.bridge.user_id} to room {room_id}")
            except Exception as e:
                self.bridge.log.error(f"Failed to invite user to room {room_id}: {str(e)}")
            
            return room_id, True
        except Exception as e:
            self.bridge.log.error(f"Failed to create room for conversation {conversation_id}: {str(e)}", exc_info=True)
            return None, False

    async def update_room_name(self, conversation_id: str, new_name: str):
        room_data = self.bridge.conversation_rooms.get(conversation_id)
        if room_data:
            room_id = room_data['room_id']
            try:
                await self.bridge.puppet_intent.set_room_name(room_id, new_name)
                self.bridge.log.info(f"Updated name for room {room_id} to {new_name}")
            except Exception as e:
                self.bridge.log.error(f"Failed to update name for room {room_id}: {str(e)}", exc_info=True)

    async def leave_old_rooms(self):
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        for conv_id, room_data in list(self.bridge.conversation_rooms.items()):
            last_message_time = room_data.get('last_message_time')
            if last_message_time and last_message_time < one_week_ago:
                try:
                    await self.bridge.puppet_intent.leave_room(room_data['room_id'])
                    del self.bridge.conversation_rooms[conv_id]
                    self.bridge.log.info(f"Left room {room_data['room_id']} for old conversation {conv_id}")
                except Exception as e:
                    self.bridge.log.error(f"Error leaving room {room_data['room_id']} for conversation {conv_id}: {str(e)}")

        await self.bridge.database.save_room_states(self.bridge.conversation_rooms)

    async def ensure_user_in_rooms(self):
        for conv_id, room_data in self.bridge.conversation_rooms.items():
            room_id = room_data['room_id']
            try:
                await self.ensure_puppet_in_room(room_id)
                members = await self.bridge.puppet_intent.get_joined_members(room_id)
                if self.bridge.user_id not in members:
                    await self.bridge.puppet_intent.invite_user(room_id, self.bridge.user_id)
                    self.bridge.log.info(f"Invited user to room {room_id} for conversation {conv_id}")
            except Exception as e:
                self.bridge.log.error(f"Error ensuring user in room {room_id} for conversation {conv_id}: {str(e)}")

    async def check_and_fix_room_permissions(self, room_id: RoomID):
        try:
            state = await self.bridge.puppet_intent.get_state(room_id)
            power_levels = next((evt for evt in state if evt.type == EventType.ROOM_POWER_LEVELS), None)
            
            if power_levels:
                content = power_levels.content
                users = content.get("users", {})
                
                # Ensure the puppet has the highest power level
                highest_power = max(users.values(), default=0)
                if self.bridge.puppet_mxid not in users or users[self.bridge.puppet_mxid] < highest_power:
                    users[self.bridge.puppet_mxid] = highest_power + 1
                    content["users"] = users
                    await self.bridge.puppet_intent.send_state_event(room_id, EventType.ROOM_POWER_LEVELS, content)
                    self.bridge.log.info(f"Updated power levels for puppet in room {room_id}")
            else:
                self.bridge.log.warning(f"No power levels found for room {room_id}")
        except Exception as e:
            self.bridge.log.error(f"Error checking and fixing room permissions for {room_id}: {str(e)}", exc_info=True)

    async def ensure_puppet_in_room(self, room_id: RoomID):
        try:
            self.bridge.log.debug(f"Attempting to ensure puppet {self.bridge.puppet_mxid} is in room {room_id}")
            
            # First, try to get joined members
            try:
                members = await self.bridge.puppet_intent.get_joined_members(room_id)
                if self.bridge.puppet_mxid in members:
                    self.bridge.log.debug(f"Puppet {self.bridge.puppet_mxid} is already in room {room_id}")
                    return
            except MForbidden:
                self.bridge.log.warning(f"Puppet {self.bridge.puppet_mxid} is not allowed to get members for room {room_id}")
            except Exception as e:
                self.bridge.log.warning(f"Failed to get joined members for room {room_id}: {str(e)}")
            
            # If we're here, either getting members failed or the puppet is not in the room
            self.bridge.log.warning(f"Puppet {self.bridge.puppet_mxid} is not in room {room_id}. Attempting to join.")
            
            # Try joining directly
            try:
                await self.bridge.puppet_intent.join_room(room_id)
                self.bridge.log.info(f"Puppet {self.bridge.puppet_mxid} successfully joined room {room_id}")
                return
            except MForbidden:
                self.bridge.log.warning(f"Puppet {self.bridge.puppet_mxid} is not allowed to join room {room_id}. Attempting to invite.")
            except Exception as e:
                self.bridge.log.error(f"Unexpected error when trying to join room {room_id}: {str(e)}")
            
            # If joining failed, try to invite the puppet
            try:
                await self.bridge.appservice.intent.invite_user(room_id, self.bridge.puppet_mxid)
                self.bridge.log.info(f"Invited puppet {self.bridge.puppet_mxid} to room {room_id}")
                
                # Try joining again after invite
                await self.bridge.puppet_intent.join_room(room_id)
                self.bridge.log.info(f"Puppet {self.bridge.puppet_mxid} successfully joined room {room_id} after invite")
            except Exception as e:
                self.bridge.log.error(f"Failed to invite and join puppet to room {room_id}: {str(e)}")
                raise

            # If we got here, the puppet should be in the room. Let's check permissions.
            await self.check_and_fix_room_permissions(room_id)
        except Exception as e:
            self.bridge.log.error(f"Failed to ensure puppet in room {room_id}: {str(e)}")
            raise
