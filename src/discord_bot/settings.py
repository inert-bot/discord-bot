"""
Contains all configuration for bot.
All settings should be loaded from enviroment variables.
For development, create a .env file in the package and make sure python-dotenv is installed.
"""

import logging
import os

log = logging.getLogger(__name__)

# Check for python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logging.debug("python-dotenv not loaded. Hope you set your environment variables.")

# Debugging
DEBUG: bool = bool(os.getenv("DEBUG", False))
# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# SQL
SQL_HOST: str = os.getenv("SQL_HOST", "localhost")
SQL_PORT: int = os.getenv("SQL_PORT", 3306)
SQL_DATABASE: str = os.getenv("SQL_DATABASE", "datatables")
SQL_USERNAME: str = os.getenv("SQL_USERNAME", "testacc")
SQL_PASSWORD: str = os.getenv("SQL_PASSWORD", "password123")

# Debug Mode Setup
__format = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
# if 'logs' not in os.listdir('data'):
#     os.mkdir('data/logs')
# data/logs/

if DEBUG is True:
    # noinspection PyArgumentList
    logging.basicConfig(
        level=logging.DEBUG,
        format=__format,
        datefmt="%d/%b/%Y %H:%M:%S",
    )
    # Set Logger Level
    logging.getLogger("discord").setLevel(logging.WARN)
    logging.getLogger("apscheduler.scheduler:Scheduler").setLevel(logging.WARN)
    logging.getLogger("cppimport.import_hook").setLevel(logging.ERROR)

    log.info("Debug Mode Enabled")
else:
    # noinspection PyArgumentList
    logging.basicConfig(
        level=logging.INFO,
        format=__format,
        datefmt="%d/%b/%Y %H:%M:%S",
    )
    logging.getLogger("discord").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.scheduler:Scheduler").setLevel(logging.ERROR)
    logging.getLogger("cppimport.import_hook").setLevel(logging.ERROR)

# Check for token and exit if not exists
if DISCORD_TOKEN is None:
    log.error("Discord API token not set")
    exit()
