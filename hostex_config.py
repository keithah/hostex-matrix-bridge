import yaml
from mautrix.util.config import BaseFileConfig, ConfigUpdateHelper
from typing import Any

class Config(BaseFileConfig):
    def __init__(self, path: str, base_path: str):
        super().__init__(path, base_path)
        self._data = None

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("homeserver.address")
        helper.copy("homeserver.domain")
        helper.copy("user.user_id")
        helper.copy("hostex.api_url")
        helper.copy("hostex.token")
        helper.copy("appservice.url")
        helper.copy("appservice.as_token")
        helper.copy("admin.user_id")
        helper.copy("bridge.username_template")
        helper.copy("bridge.double_puppet_server_map")

    def __getitem__(self, key: str) -> Any:
        if "." in key:
            section, subkey = key.split(".", 1)
            return self[section][subkey]
        return super().__getitem__(key)

    def load(self):
        with open(self.path, 'r') as file:
            self._data = yaml.safe_load(file)

    def save(self):
        pass  # Do nothing to prevent writing to the file
