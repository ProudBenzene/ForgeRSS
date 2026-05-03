#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
ForgeRSS - Main Application Entry
Supports two modes:
1. Single run: python app.py --once
2. Daemon mode: python app.py (default, with scheduler)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ??????
from dotenv import load_dotenv

# ?????????? .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    # ???? .env.example ????????????????
    example_path = Path(__file__).parent / ".env.example"
    if example_path.exists():
        load_dotenv(dotenv_path=example_path, override=False)

# ????
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("forgerss")


def get_config():
    """????????????"""
    return {
        "max_articles": int(os.getenv("MAX_ARTICLES", "50")),
        "run_interval": int(os.getenv("RUN_INTERVAL", "3600")),  # ??1??
        "full_refresh": os.getenv("FULL_REFRESH", "false").lower() == "true",
        "use_db": os.getenv("USE_DB", "true").lower() == "true",
    }


def run_all_generators(config: dict) -> dict:
    """???????"""
    from scripts.run_all import GENERATORS
    
    results = {}
    
    for name, generator_class in GENERATORS.items():
        logger.info(f"Running generator: {name}")
        try:
            generator = generator_class()
            success = generator.run(
                full_refresh=config["full_refresh"],
                max_articles=config["max_articles"],
                use_db=config["use_db"]
            )
            results[name] = "success" if success else "failed"
            logger.info(f"Generator {name}: {'SUCCESS' if success else 'FAILED'}")
        except Exception as e:
            logger.error(f"Generator {name} error: {e}", exc_info=True)
            results[name] = "error"
    
    return results


def run_once():
    """??????"""
    logger.info("ForgeRSS starting (single run mode)")
    config = get_config()
    
    start_time = time.time()
    results = run_all_generators(config)
    elapsed = time.time() - start_time
    
    # ????
    success_count = sum(1 for v in results.values() if v == "success")
    total_count = len(results)
    
    logger.info(f"Completed: {success_count}/{total_count} generators succeeded in {elapsed:.1f}s")
    
    return all(v == "success" for v in results.values())


def run_daemon():
    """?????????????"""
    logger.info("ForgeRSS starting (daemon mode)")
    config = get_config()
    interval = config["run_interval"]
    
    logger.info(f"Run interval: {interval} seconds ({interval/3600:.1f} hours)")
    
    while True:
        try:
            logger.info(f"Starting scheduled run at {datetime.now().isoformat()}")
            
            start_time = time.time()
            results = run_all_generators(config)
            elapsed = time.time() - start_time
            
            success_count = sum(1 for v in results.values() if v == "success")
            total_count = len(results)
            
            logger.info(f"Run completed: {success_count}/{total_count} in {elapsed:.1f}s")
            logger.info(f"Next run in {interval} seconds...")
            
            time.sleep(interval)
            
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.info(f"Retrying in {interval} seconds...")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="ForgeRSS - RSS Feed Generator")
    parser.add_argument(
        "--once", 
        action="store_true",
        help="Run once and exit (default: daemon mode with scheduler)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full refresh (ignore cache)"
    )
    args = parser.parse_args()
    
    # ??????
    if args.full:
        os.environ["FULL_REFRESH"] = "true"
    
    if args.once:
        success = run_once()
        sys.exit(0 if success else 1)
    else:
        run_daemon()


if __name__ == "__main__":
    main()
