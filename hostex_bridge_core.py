from mautrix.types import UserID, RoomID, Event, TextMessageEventContent, MessageType
from mautrix.util.async_db import Database
from mautrix.appservice import AppService, IntentAPI
from mautrix.errors import MatrixInvalidToken, MExclusive
from mautrix.util.simple_template import SimpleTemplate
import logging
from yarl import URL
from datetime import datetime, timezone, timedelta
import asyncio
import json
import time

from hostex_api import HostexAPI
from appservice_websocket import AppserviceWebsocket
from hostex_commands import HostexCommands
from hostex_database import HostexDatabase
from hostex_room_management import HostexRoomManager
from hostex_message_handling import HostexMessageHandler
from hostex_polling import HostexPoller

logger = logging.getLogger(__name__)

class HostexBridgeCore:
    def __init__(self, config, database: Database, registration: dict, debug: bool):
        self.config = config
        self.registration = registration
        self.debug = debug
        self.database = HostexDatabase(database)
        self.database_started = False
        self.conversation_rooms = {}
        self.admin_user = UserID(self.config["admin.user_id"])
        self.last_poll_time = None
        self.all_conversations = []
        self.guest_prefix = "Guest"
        self.admin_room_id = None

        self.log = logging.getLogger("HostexBridge")
        if self.debug:
            self.log.setLevel(logging.DEBUG)
        else:
            self.log.setLevel(logging.INFO)

        self.hs_domain = self.config["homeserver.domain"]
        self.mxid_template = SimpleTemplate(self.config["bridge.username_template"], "userid",
                                            prefix="@", suffix=f":{self.hs_domain}", type=str)

        hostex_api_url = self.config["hostex.api_url"]
        hostex_token = self.config["hostex.token"]
        self.hostex_api = HostexAPI(hostex_api_url, hostex_token)

        server_url = self.config["homeserver.address"]
        self.bot_mxid = UserID(f"@{registration['sender_localpart']}:{self.hs_domain}")
        self.user_id = UserID(self.config["user.user_id"])
        self.appservice = AppService(
            id=self.registration['id'],
            domain=self.hs_domain,
            server=server_url,
            as_token=self.registration['as_token'],
            hs_token=self.registration['hs_token'],
            bot_localpart=self.registration['sender_localpart'],
        )

        self.websocket = AppserviceWebsocket(
            self.config['appservice.url'],
            self.config['appservice.as_token'],
            self.handle_matrix_event
        )

        self.commands = HostexCommands(self)
        self.room_manager = HostexRoomManager(self)
        self.message_handler = HostexMessageHandler(self)
        self.poller = HostexPoller(self)
        self.stop_event = asyncio.Event()

        # Set up single puppet
        self.puppet_mxid = self.bot_mxid
        self.puppet_intent = None  # We'll set this in async_init

        self.daily_maintenance_task = None
        self.hourly_maintenance_task = None

    async def async_init(self):
        await self.appservice.start(host="0.0.0.0", port=8080)
        self.puppet_intent = self.appservice.intent.user(self.puppet_mxid)
        
        # Add this logging
        self.log.info(f"Puppet user: {self.puppet_mxid}")
        self.log.info(f"AppService ID: {self.appservice.id}")
        self.log.info(f"AppService AS token: {self.appservice.as_token[:5]}...")
        self.log.info(f"AppService HS token: {self.appservice.hs_token[:5]}...")

        try:
            whoami = await self.puppet_intent.whoami()
            self.log.info(f"Puppet whoami: {whoami}")
        except Exception as e:
            self.log.error(f"Failed to get puppet whoami: {str(e)}")

    async def start(self):
        try:
            if not self.database_started:
                await self.database.start()
                self.database_started = True
            await self.database.ensure_schema()
            await self.room_manager.load_room_states()

            self.log.info(f"AppService ID: {self.appservice.id}")
            self.log.info(f"AppService AS token: {self.appservice.as_token[:5]}...")
            self.log.info(f"AppService HS token: {self.appservice.hs_token[:5]}...")
            
            try:
                whoami = await self.puppet_intent.whoami()
                self.log.info(f"Connected as {whoami}")
            except Exception as e:
                self.log.error(f"Failed to connect to Matrix homeserver: {e}", exc_info=True)
                return

            await self.room_manager.ensure_admin_room()
            await self.room_manager.load_conversations()

            await self.websocket.start()

            await self.poller.start_polling()

            # Start maintenance tasks
            self.daily_maintenance_task = asyncio.create_task(self.run_daily_maintenance())
            self.hourly_maintenance_task = asyncio.create_task(self.run_hourly_maintenance())

            # Start the clean_old_messages_loop
            asyncio.create_task(self.clean_old_messages_loop())

        except Exception as e:
            self.log.error(f"Error starting the bridge: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self):
        try:
            if self.daily_maintenance_task:
                self.daily_maintenance_task.cancel()
            if self.hourly_maintenance_task:
                self.hourly_maintenance_task.cancel()

            if hasattr(self.appservice, 'runner'):
                await self.appservice.stop()
            if self.database_started:
                await self.database.stop()
                self.database_started = False
        except Exception as e:
            self.log.error(f"Error stopping the bridge: {e}", exc_info=True)

    async def run_daily_maintenance(self):
        while True:
            try:
                await asyncio.sleep(24 * 60 * 60)  # Wait for 24 hours
                self.log.info("Running daily maintenance tasks")
                await self.room_manager.leave_old_rooms()
                await self.room_manager.ensure_user_in_rooms()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in daily maintenance: {e}", exc_info=True)

    async def run_hourly_maintenance(self):
        while True:
            try:
                await asyncio.sleep(60 * 60)  # Wait for 1 hour
                self.log.info("Running hourly maintenance tasks")
                await self.room_manager.load_conversations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in hourly maintenance: {e}", exc_info=True)

    async def clean_old_messages_loop(self):
        while True:
            try:
                await asyncio.sleep(60)  # Clean every minute
                self.message_handler.clean_old_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in clean_old_messages_loop: {e}", exc_info=True)

    async def handle_matrix_event(self, event: Event):
        if event.sender == self.puppet_mxid:
            return  # Ignore events from the puppet account
        
        if event.sender.endswith(":beeper.com"):
            await self.message_handler.handle_matrix_event(event)
        elif event.sender.endswith(":beeper.local"):
            self.log.debug(f"Received event from bot or bridge: {event}")

    def get_mxid_from_id(self, hostex_id: str) -> UserID:
        return UserID(self.mxid_template.format_full(hostex_id))

    async def force_maintenance(self):
        self.log.info("Forcing maintenance tasks")
        await self.room_manager.leave_old_rooms()
        await self.room_manager.ensure_user_in_rooms()
        await self.room_manager.load_conversations()

    async def update_conversations(self):
        conversations = await self.hostex_api.get_conversations()
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        updated_conversations = []

        for conv in conversations.get('data', {}).get('conversations', []):
            last_message_at = self.hostex_api.parse_timestamp(conv['last_message_at'])
            if last_message_at.tzinfo is None:
                last_message_at = last_message_at.replace(tzinfo=timezone.utc)
            
            if last_message_at >= one_week_ago:
                if conv['id'] not in self.conversation_rooms:
                    updated_conversations.append(conv)
                else:
                    stored_time = self.conversation_rooms[conv['id']].get('last_message_time', datetime.min.replace(tzinfo=timezone.utc))
                    if stored_time.tzinfo is None:
                        stored_time = stored_time.replace(tzinfo=timezone.utc)
                    
                    if last_message_at > stored_time:
                        updated_conversations.append(conv)

        self.all_conversations = sorted(updated_conversations, key=lambda x: self.hostex_api.parse_timestamp(x['last_message_at']).replace(tzinfo=timezone.utc))
        return self.all_conversations
