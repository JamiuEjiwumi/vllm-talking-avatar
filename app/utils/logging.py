# app/utils/logging.py
import logging, os, sys, json

def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ["urllib3", "requests"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

setup_logging()
