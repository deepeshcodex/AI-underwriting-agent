"""Kafka-ready event stub — swap for aiokafka producer in production."""

from __future__ import annotations

from typing import Any

from services.logger import get_logger
from services.settings import settings

log = get_logger(__name__)


async def emit_underwriting_event(topic: str, payload: dict[str, Any]) -> None:
    """Publish to Kafka when KAFKA_BOOTSTRAP_SERVERS is set; else structured log."""
    if settings.kafka_bootstrap_servers:
        log.info(
            "kafka_event_queued",
            extra={"topic": topic, "bootstrap": settings.kafka_bootstrap_servers},
        )
        return
    log.info("underwriting_event", extra={"topic": topic, "payload_keys": list(payload.keys())})
