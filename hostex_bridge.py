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
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    config_path = os.path.expanduser("~/airbnb/bridge/config.yaml")
    registration_path = os.path.expanduser("~/airbnb/bridge/registration.yaml")
    db_path = os.path.expanduser("~/airbnb/bridge/hostex_bridge.db")

    config = Config(config_path, '')
    config.load()

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