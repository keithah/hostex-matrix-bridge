# Hostex Matrix Bridge

This is a Matrix bridge for Hostex, allowing you to interact with Hostex conversations through Matrix. This bridge was developed using the mautrix framework and was written with the assistance of OpenAI's Claude AI.

## Credits and Licensing

This project uses the [mautrix-python](https://github.com/mautrix/python) library, which is licensed under the Mozilla Public License 2.0. The mautrix project can be found at: https://github.com/mautrix/

This Hostex Matrix Bridge is licensed under the BSD 3-Clause License. See the [LICENSE](LICENSE) file for details.

## Prerequisites

- Python 3.7+
- A Matrix homeserver (e.g., Synapse)
- Hostex API credentials

## Installation

1. Clone this repository:
git clone https://github.com/keithah/hostex-matrix-bridge.git
cd hostex-matrix-bridge

2. Create a virtual environment and activate it:
python3 -m venv venv
source venv/bin/activate

3. Install the required dependencies:
pip install -r requirements.txt

## Configuration

### For Self-Hosted Synapse

1. Copy the example configuration files:
cp config.example.yaml config.yaml
cp registration.example.yaml registration.yaml
2. Edit `config.yaml` and `registration.yaml` to match your setup. See the Configuration section below for details.
3. Register the application service with your Synapse server:
- Add the path to your `registration.yaml` file in your Synapse `homeserver.yaml` configuration:
  ```yaml
  app_service_config_files:
    - /path/to/hostex-bridge/registration.yaml
  ```
- Restart your Synapse server to apply the changes.

### For beeper/bbctl

1. Copy the example configuration file:
cp config.example.yaml config.yaml
2. Edit `config.yaml` to match your setup. See the Configuration section below for details.
3. Use `bbctl` to register and start the bridge:
bbctl bridge add hostex /path/to/hostex-bridge/config.yaml
bbctl bridge start hostex

## Configuration Details

### config.yaml

```yaml
homeserver:
 address: https://matrix.example.com
 domain: example.com

user:
 user_id: "@hostex:example.com"

hostex:
 api_url: https://api.hostex.com
 token: your_hostex_api_token

appservice:
 address: http://localhost:8080
 hostname: 0.0.0.0
 port: 8080
 database: sqlite:///bridge.db
 id: hostex
 bot_username: hostexbot
 as_token: generate_a_random_token_here
 hs_token: generate_another_random_token_here

bridge:
 username_template: "hostex_{userid}"
 displayname_template: "{displayname} (Hostex)"

logging:
 console_log_level: DEBUG
 file_log_level: INFO
 file_log_path: bridge.log

admin:
 user_id: "@admin:example.com"

### registration.yaml (for self-hosted Synapse)
id: hostex
as_token: generate_a_random_token_here
hs_token: generate_another_random_token_here
namespaces:
    users:
        - exclusive: true
          regex: "@hostex_.*:example\\.com"
    aliases: []
    rooms: []
url: http://localhost:8080
sender_localpart: hostexbot
rate_limited: false

Make sure to replace example.com with your actual domain, and generate unique tokens for as_token and hs_token.
#Running the Bridge
##For Self-Hosted Synapse

Run the bridge using:
python hostex_bridge.pyo

##For beeper/bbctl
The bridge should start automatically after registration. You can manage it using bbctl commands:
bbctl bridge status hostex
bbctl bridge stop hostex
bbctl bridge start hostex

#Usage
Once the bridge is running and configured:

Invite the bridge bot (e.g., @hostexbot:example.com) to a room.
The bridge will create a room for each Hostex conversation.
You can now send and receive messages between Matrix and Hostex.

#Troubleshooting

Check the bridge logs (console output or bridge.log) for any error messages.
Ensure your Hostex API credentials are correct.
Verify that the application service is properly registered with your homeserver.
For beeper/bbctl setups, use bbctl bridge logs hostex to view logs.

#Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
#Support
If you encounter any issues or have questions, please open an issue on the GitHub repository.


