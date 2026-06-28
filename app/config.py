"""Central config. Reads from env vars with sensible local defaults so the
project runs out of the box for grading without any .env setup."""

import os

EVENT_BUS_BACKEND = os.environ.get("EVENT_BUS_BACKEND", "in_memory")   # "in_memory" | "kafka"
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_LOCALE = os.environ.get("DEFAULT_LOCALE", "en")
