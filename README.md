# Hostex Matrix Bridge

Hostex is a cloud-based short-term rental management software (PMS) that provides a broad range of features, automation tools, and seamless integration with popular booking platforms.

This is a Matrix bridge for [Hostex](https://hostex.io), allowing you to interact with Hostex conversations through Matrix. I use it with Airbnb primarily.

This bridge was developed using the mautrix framework and was written with the assistance of OpenAI's Claude AI.

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

# Running the Bridge
## For Self-Hosted Synapse

Run the bridge using:
python hostex_bridge.pyo

## For beeper/bbctl
The bridge should start automatically after registration. You can manage it using bbctl commands:
bbctl bridge status hostex
bbctl bridge stop hostex
bbctl bridge start hostex

# Usage
Once the bridge is running and configured:

Invite the bridge bot (e.g., @hostexbot:example.com) to a room.
The bridge will create a room for each Hostex conversation.
You can now send and receive messages between Matrix and Hostex.

# Troubleshooting

Check the bridge logs (console output or bridge.log) for any error messages.
Ensure your Hostex API credentials are correct.
Verify that the application service is properly registered with your homeserver.
For beeper/bbctl setups, use bbctl bridge logs hostex to view logs.

# Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
# Support
If you encounter any issues or have questions, please open an issue on the GitHub repository.


