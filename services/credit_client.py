"""TransUnion / Experian clients with retries — behavior driven by config/credit.yaml."""

from __future__ import annotations

import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.config_loader import load_credit
from services.logger import get_logger
from services.settings import settings

log = get_logger(__name__)


def _env_or_config(key: str, cfg_key: str, credit_cfg: dict[str, Any]) -> str | None:
    v = os.environ.get(key) or credit_cfg.get(cfg_key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _request_json(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    r = client.request(method, url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def pull_credit_primary() -> dict[str, Any]:
    """Returns normalized credit payload: score, bureau, raw (limited), mock flag."""
    cfg = load_credit()
    if settings.credit_use_mock or os.environ.get(cfg["mock"]["enabled_env"], "").lower() in (
        "1",
        "true",
        "yes",
    ):
        mock = cfg.get("mock", {})
        return {
            "bureau": "mock",
            "score": float(mock.get("default_score", 720)),
            "adverse_flags": list(mock.get("default_adverse_flags", [])),
            "mock": True,
        }

    providers_cfg: dict[str, Any] = cfg.get("providers", {})
    order = cfg.get("pull_order", ["transunion", "experian"])
    last_err: Exception | None = None

    for name in order:
        pc = providers_cfg.get(name)
        if not pc:
            continue
        base = _env_or_config(pc["base_url_env"], "base_url", pc)
        api_key = _env_or_config(pc["api_key_env"], "api_key", pc)
        if not base or not api_key:
            log.info("credit_skip_missing_env", extra={"provider": name})
            continue
        timeout = float(pc.get("timeout_seconds", 30))
        path = pc.get("score_path", "/")
        url = base.rstrip("/") + path
        try:
            with httpx.Client() as client:
                data = _request_json(
                    client,
                    "GET",
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                    timeout=timeout,
                )
            return {
                "bureau": name,
                "score": float(data.get("score", data.get("creditScore", 0))),
                "adverse_flags": list(data.get("adverse_flags", data.get("flags", []))),
                "mock": False,
                "raw_ref": {k: data[k] for k in list(data)[:5]},
            }
        except Exception as e:
            last_err = e
            log.info("credit_provider_failed", extra={"provider": name, "error": str(e)})

    if last_err:
        raise RuntimeError("All credit providers failed") from last_err
    raise RuntimeError("No credit providers configured; set CREDIT_USE_MOCK=true for development.")
