import aiohttp
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
import pytz

logger = logging.getLogger(__name__)

class HostexAPI:
    def __init__(self, api_url: str, token: str, config):
        if not api_url:
            raise ValueError("Hostex API URL is required")
        if not token:
            raise ValueError("Hostex API token is required")
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.log = logger
        self.config = config
        self.timezone = config.hostex_timezone

    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, data: Dict[str, Any] = None) -> Any:
        url = f"{self.api_url}/{endpoint}"
        self.log.debug(f"Making {method} request to {url}")
        self.log.debug(f"Headers: {self.headers}")
        self.log.debug(f"Params: {params}")
        self.log.debug(f"Data: {data}")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(method, url, headers=self.headers, params=params, json=data) as response:
                    response_text = await response.text()
                    self.log.debug(f"Response status: {response.status}")
                    self.log.debug(f"Response text: {response_text}")
                    response.raise_for_status()
                    json_response = await response.json()
                    self.log.debug(f"Received response: {json_response}")
                    return json_response
            except aiohttp.ClientResponseError as e:
                self.log.error(f"HTTP error when making request to Hostex API: {e.status} {e.message}")
                self.log.error(f"Response body: {await e.response.text()}")
                return {"error_code": e.status, "error_msg": e.message}
            except aiohttp.ClientError as e:
                self.log.error(f"Network error when making request to Hostex API: {e}")
                return {"error_code": 500, "error_msg": str(e)}
            except Exception as e:
                self.log.error(f"Unexpected error when making request to Hostex API: {e}")
                return {"error_code": 500, "error_msg": str(e)}

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        self.log.debug(f"Parsing timestamp: {timestamp_str}")
        try:
            dt = datetime.fromisoformat(timestamp_str.rstrip('Z'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone(self.timezone)
            self.log.debug(f"Parsed timestamp: {local_dt}")
            return local_dt
        except Exception as e:
            self.log.error(f"Error parsing timestamp {timestamp_str}: {e}")
            return datetime.now(self.timezone)

    async def get_conversations(self, offset: int = 0, limit: int = 20) -> Dict[str, Any]:
        self.log.debug(f"Getting conversations with offset {offset} and limit {limit}")
        endpoint = "conversations"
        params = {"offset": offset, "limit": limit}
        return await self._make_request("GET", endpoint, params=params)

    async def get_conversation_messages(self, conversation_id: str, limit: int = 20, last_message_id: str = None) -> List[Dict[str, Any]]:
        self.log.debug(f"Getting messages for conversation {conversation_id} with limit {limit} and last_message_id {last_message_id}")
        endpoint = f"conversations/{conversation_id}"
        params = {"limit": limit}
        if last_message_id:
            params["last_message_id"] = last_message_id
        response = await self._make_request("GET", endpoint, params=params)
        self.log.debug(f"Full response for conversation {conversation_id}: {response}")
        messages = response.get("data", {}).get("messages", [])
        self.log.debug(f"Retrieved {len(messages)} messages for conversation {conversation_id}")
        return messages

    async def send_message(self, conversation_id: str, message: str) -> Dict[str, Any]:
        self.log.debug(f"Sending message to conversation {conversation_id}: {message}")
        endpoint = f"conversations/{conversation_id}"
        data = {"message": message}
        self.log.debug(f"Sending message to Hostex API: {data}")
        response = await self._make_request("POST", endpoint, data=data)
        self.log.debug(f"Received response from Hostex API: {response}")
        return response

    async def get_guest_name(self, conversation_id: str) -> str:
        self.log.debug(f"Getting guest name for conversation {conversation_id}")
        endpoint = f"conversations/{conversation_id}"
        response = await self._make_request("GET", endpoint)
        guest = response.get("data", {}).get("guest", {})
        guest_name = guest.get("name", "Unknown Guest")
        self.log.debug(f"Retrieved guest name: {guest_name}")
        return guest_name

    async def get_conversation_details(self, conversation_id: str) -> Dict[str, Any]:
        self.log.debug(f"Getting conversation details for {conversation_id}")
        endpoint = f"conversations/{conversation_id}"
        response = await self._make_request("GET", endpoint)
        self.log.debug(f"Retrieved conversation details: {response}")
        return response
