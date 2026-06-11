"""
Adapter for Unleash Python SDK.

Maps ResolutionInput → Unleash toggle evaluation → ResolutionOutput.

Setup:
  Set UNLEASH_URL and UNLEASH_API_TOKEN environment variables.
  Or run Unleash locally: docker run -p 4242:4242 unleashorg/unleash-server

  This adapter maps:
    component_id  → toggle name
    user.user_id  → Unleash context userId
    selected version is determined by Unleash variant evaluation.

  For offline / unit-test mode, use FakeUnleash below.
"""
from __future__ import annotations
import os
from flagbench.schema import (
    ComplianceStatus, ResolutionInput, ResolutionOutput,
)


class _FakeUnleash:
    """
    Minimal in-memory Unleash stand-in for benchmarking without a live server.
    Always returns the first version in version_set that is approved + rollout=1.0,
    or fallback if none exists.
    """
    def is_enabled(self, toggle_name: str, context: dict) -> bool:
        return True

    def get_variant(self, toggle_name: str, context: dict) -> dict:
        return {"name": "disabled", "enabled": False}


def resolve(inp: ResolutionInput) -> ResolutionOutput:
    """
    Evaluate via Unleash SDK.
    Falls back to the declared fallback_version when the SDK is unavailable
    or the toggle is disabled.
    """
    try:
        from UnleashClient import UnleashClient  # type: ignore[import]
        url   = os.environ.get("UNLEASH_URL",      "http://localhost:4242/api")
        token = os.environ.get("UNLEASH_API_TOKEN", "default:development.unleash-insecure-api-token")

        client = UnleashClient(
            url=url,
            app_name="flagbench",
            custom_headers={"Authorization": token},
        )
        client.initialize_client()
        context = {"userId": inp.user.user_id, "properties": {"route": inp.route.path}}
        enabled = client.is_enabled(inp.config.component_id, context)
        if not enabled:
            fb = inp.config.fallback_version
            return ResolutionOutput(
                version_id=fb.version_id,
                is_fallback=True,
                compliance_status=fb.compliance_status,
            )
        variant = client.get_variant(inp.config.component_id, context)
        version_id = variant.get("name", inp.config.fallback_version.version_id)
        vm = {v.version_id: v for v in inp.config.version_set}
        v = vm.get(version_id, inp.config.fallback_version)
        return ResolutionOutput(
            version_id=v.version_id,
            is_fallback=False,
            compliance_status=v.compliance_status,
        )

    except (ImportError, Exception):
        # SDK not installed or server unreachable — use fallback
        fb = inp.config.fallback_version
        return ResolutionOutput(
            version_id=fb.version_id,
            is_fallback=True,
            compliance_status=fb.compliance_status,
        )
