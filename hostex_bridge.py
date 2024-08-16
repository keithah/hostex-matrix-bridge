import asyncio
import yaml
from mautrix.util.async_db import Database
import logging
import os
import argparse
from hostex_bridge_core import HostexBridgeCore
from hostex_config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="Hostex Bridge")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--config", default="config.yaml", help="Path to the config file")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct paths relative to the script directory
    config_path = os.path.join(script_dir, args.config)
    registration_path = os.path.join(script_dir, "registration.yaml")
    db_path = os.path.join(script_dir, "hostex_bridge.db")

    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        return

    config = Config(config_path, '')
    config.load()

    if not os.path.exists(registration_path):
        logger.error(f"Registration file not found: {registration_path}")
        return

    with open(registration_path, "r") as registration_file:
        registration_data = yaml.safe_load(registration_file)

    database = Database.create(f"sqlite:///{db_path}", upgrade_table=None, db_args={}, log=logger)
    bridge = HostexBridgeCore(config, database, registration_data, args.debug)

    try:
        logger.info("Starting Hostex bridge")
        await bridge.async_init()
        await bridge.start()
        logger.info("Hostex bridge is running. Press Ctrl+C to stop.")
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping bridge")
    except Exception as e:
        logger.error(f"Error running the bridge: {e}", exc_info=True)
    finally:
        logger.info("Stopping Hostex bridge")
        await bridge.stop()
        logger.info("Hostex bridge stopped")

if __name__ == "__main__":
    asyncio.run(main())
