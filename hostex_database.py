# hostex_database.py

import logging
from mautrix.util.async_db import Database
from datetime import datetime, timezone
import sqlite3
import json

logger = logging.getLogger(__name__)

def adapt_datetime(ts):
    return ts.isoformat()

def convert_datetime(val):
    try:
        dt = datetime.fromisoformat(val.decode())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning(f"Invalid timestamp found: {val}")
        return None

class HostexDatabase:
    def __init__(self, database: Database):
        self.db = database
        sqlite3.register_adapter(datetime, adapt_datetime)
        sqlite3.register_converter("timestamp", convert_datetime)

    async def start(self):
        await self.db.start()
        await self.ensure_schema()

    async def stop(self):
        await self.db.stop()

    async def ensure_schema(self):
        async with self.db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS room_states (
                    conversation_id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    last_message TEXT,
                    last_message_time TIMESTAMP
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    sender_role TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES room_states(conversation_id)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS last_poll_time (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    conversation_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (conversation_id, message_id)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS puppets (
                    user_id TEXT PRIMARY KEY,
                    puppet_data TEXT NOT NULL
                )
            """)

    async def save_message(self, conversation_id: str, message_id: str, content: str, timestamp: datetime, sender_role: str):
        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO messages (id, conversation_id, content, timestamp, sender_role) VALUES (?, ?, ?, ?, ?)",
                message_id, conversation_id, content, timestamp, sender_role
            )

    async def get_recent_messages(self, conversation_id: str, limit: int = 100):
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, content, timestamp, sender_role FROM messages WHERE conversation_id = ? ORDER BY timestamp DESC LIMIT ?",
                conversation_id, limit
            )
        return [dict(row) for row in rows]

    async def load_room_states(self):
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT conversation_id, room_id, last_message, last_message_time FROM room_states")
            result = []
            for row in rows:
                last_message_time = row['last_message_time']
                if last_message_time and last_message_time.tzinfo is None:
                    last_message_time = last_message_time.replace(tzinfo=timezone.utc)
                result.append({
                    'conversation_id': row['conversation_id'],
                    'room_id': row['room_id'],
                    'last_message': row['last_message'],
                    'last_message_time': last_message_time
                })
            return result

    async def save_room_states(self, room_states):
        async with self.db.acquire() as conn:
            for conv_id, room_data in room_states.items():
                last_message_time = room_data.get('last_message_time')
                if isinstance(last_message_time, datetime):
                    if last_message_time.tzinfo is None:
                        last_message_time = last_message_time.replace(tzinfo=timezone.utc)
                    last_message_time = last_message_time.isoformat()
                
                await conn.execute(
                    "INSERT OR REPLACE INTO room_states (conversation_id, room_id, last_message, last_message_time) VALUES (?, ?, ?, ?)",
                    conv_id, str(room_data['room_id']), room_data.get('last_message'), last_message_time
                )

    async def get_last_processed_message_id(self, conversation_id: str):
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM messages WHERE conversation_id = ? ORDER BY timestamp DESC LIMIT 1",
                conversation_id
            )
        return row['id'] if row else None

    async def get_last_poll_time(self):
        async with self.db.acquire() as conn:
            result = await conn.fetchval("SELECT timestamp FROM last_poll_time WHERE id = 1")
            if result:
                if result.tzinfo is None:
                    result = result.replace(tzinfo=timezone.utc)
                return result
            return datetime.min.replace(tzinfo=timezone.utc)

    async def set_last_poll_time(self, timestamp):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT OR REPLACE INTO last_poll_time (id, timestamp) VALUES (1, ?)
            """, timestamp)

    async def get_processed_message_ids(self, conversation_id):
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT message_id FROM processed_messages WHERE conversation_id = ?", conversation_id)
            return set(row['message_id'] for row in rows)

    async def add_processed_message_id(self, conversation_id, message_id):
        async with self.db.acquire() as conn:
            await conn.execute("INSERT OR IGNORE INTO processed_messages (conversation_id, message_id) VALUES (?, ?)",
                               conversation_id, message_id)

    async def save_puppet_data(self, user_id: str, puppet_data: str):
        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO puppets (user_id, puppet_data) VALUES (?, ?)",
                user_id, puppet_data
            )

    async def get_all_puppets(self):
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, puppet_data FROM puppets")
            return [(row['user_id'], row['puppet_data']) for row in rows]
