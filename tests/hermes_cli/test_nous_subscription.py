"""Tests for Nous subscription feature detection."""

from hermes_cli.nous_account import NousPortalAccountInfo, NousToolAccessInfo
from hermes_cli import nous_subscription as ns


_POOL_COVERAGE = {
    "firecrawl": True,
    "fal": True,
    "fal-video": False,
    "openai-audio": True,
    "browser-use": True,
    "modal": True,
}


def _account(*, logged_in: bool, paid: bool | None = None) -> NousPortalAccountInfo:
    return NousPortalAccountInfo(
        logged_in=logged_in,
        source="jwt" if logged_in else "none",
        fresh=False,
        paid_service_access=paid,
    )


def _pool_account() -> NousPortalAccountInfo:
    """A $0 subscriber with a live free tool pool (no paid access)."""
    return NousPortalAccountInfo(
        logged_in=True,
        source="jwt",
        fresh=False,
        paid_service_access=False,
        tool_access=NousToolAccessInfo(enabled=True, coverage=_POOL_COVERAGE),
    )


def test_get_nous_subscription_features_recognizes_direct_exa_backend(monkeypatch):
    env = {"EXA_API_KEY": "exa-test"}

    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=False)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "web")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)

    features = ns.get_nous_subscription_features({"web": {"backend": "exa"}})

    assert features.web.available is True
    assert features.web.active is True
    assert features.web.managed_by_nous is False
    assert features.web.direct_override is True
    assert features.web.current_provider == "exa"


def test_get_nous_subscription_features_force_fresh_forwards_account_request(monkeypatch):
    calls = []

    def fake_account_info(*, force_fresh=False):
        calls.append(force_fresh)
        return _account(logged_in=True, paid=True)

    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "get_nous_portal_account_info", fake_account_info)
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: False)
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(ns, "is_managed_tool_gateway_ready", lambda vendor: False)

    features = ns.get_nous_subscription_features({}, force_fresh=True)

    assert features.account_info is not None
    assert features.account_info.paid_service_access is True
    assert calls == [True]


def test_get_nous_subscription_features_prefers_managed_modal_in_auto_mode(monkeypatch):
    monkeypatch.setattr("tools.tool_backend_helpers.managed_nous_tools_enabled", lambda: True)
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "terminal")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: True)
    monkeypatch.setattr(ns, "is_managed_tool_gateway_ready", lambda vendor: vendor == "modal")

    features = ns.get_nous_subscription_features(
        {"terminal": {"backend": "modal", "modal_mode": "auto"}}
    )

    assert features.modal.available is True
    assert features.modal.active is True
    assert features.modal.managed_by_nous is True
    assert features.modal.direct_override is False


def test_get_nous_subscription_features_marks_browser_use_as_managed_when_gateway_ready(monkeypatch):
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "browser")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: True)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(
        ns,
        "is_managed_tool_gateway_ready",
        lambda vendor: vendor == "browser-use",
    )

    features = ns.get_nous_subscription_features(
        {"browser": {"cloud_provider": "browser-use"}}
    )

    assert features.browser.available is True
    assert features.browser.active is True
    assert features.browser.managed_by_nous is True
    assert features.browser.direct_override is False
    assert features.browser.current_provider == "Browser Use"


def test_get_nous_subscription_features_uses_direct_browserbase_when_no_managed_gateway(monkeypatch):
    """When direct Browserbase keys are set and no managed gateway is available,
    the unconfigured fallback should pick Browserbase as a direct provider."""
    env = {
        "BROWSERBASE_API_KEY": "bb-key",
        "BROWSERBASE_PROJECT_ID": "bb-project",
    }

    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "browser")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: True)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(
        ns,
        "is_managed_tool_gateway_ready",
        lambda vendor: False,  # No managed gateway available
    )

    features = ns.get_nous_subscription_features({})

    assert features.browser.available is True
    assert features.browser.active is True
    assert features.browser.managed_by_nous is False
    assert features.browser.direct_override is True
    assert features.browser.current_provider == "Browserbase"


def test_get_nous_subscription_features_prefers_camofox_over_managed_browser_use(monkeypatch):
    env = {"CAMOFOX_URL": "http://localhost:9377"}

    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "browser")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(
        ns,
        "is_managed_tool_gateway_ready",
        lambda vendor: vendor == "browser-use",
    )

    features = ns.get_nous_subscription_features(
        {"browser": {"cloud_provider": "browser-use"}}
    )

    assert features.browser.available is True
    assert features.browser.active is True
    assert features.browser.managed_by_nous is False
    assert features.browser.direct_override is True
    assert features.browser.current_provider == "Camofox"


def test_get_nous_subscription_features_requires_agent_browser_for_browserbase(monkeypatch):
    env = {
        "BROWSERBASE_API_KEY": "bb-key",
        "BROWSERBASE_PROJECT_ID": "bb-project",
    }

    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=False)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "browser")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(ns, "is_managed_tool_gateway_ready", lambda vendor: False)

    features = ns.get_nous_subscription_features(
        {"browser": {"cloud_provider": "browserbase"}}
    )

    assert features.browser.available is False
    assert features.browser.active is False
    assert features.browser.managed_by_nous is False
    assert features.browser.current_provider == "Browserbase"


def test_get_nous_subscription_features_does_not_treat_quoted_false_as_gateway_opt_in(monkeypatch):
    env = {"EXA_API_KEY": "exa-test"}

    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: key == "web")
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(ns, "is_managed_tool_gateway_ready", lambda vendor: vendor == "firecrawl")

    features = ns.get_nous_subscription_features(
        {"web": {"backend": "exa", "use_gateway": "false"}}
    )

    assert features.web.available is True
    assert features.web.active is True
    assert features.web.managed_by_nous is False
    assert features.web.direct_override is True
    assert features.web.current_provider == "exa"


def test_get_gateway_eligible_tools_ignores_quoted_false_opt_in(monkeypatch):
    # Paid account: entitled to every category, including video.
    monkeypatch.setattr(
        ns, "get_nous_portal_account_info", lambda **kw: _account(logged_in=True, paid=True)
    )
    monkeypatch.setattr(
        ns,
        "_get_gateway_direct_credentials",
        lambda: {
            "web": True,
            "image_gen": False,
            "tts": False,
            "stt": False,
            "browser": False,
        },
    )

    unconfigured, has_direct, already_managed = ns.get_gateway_eligible_tools(
        {
            "model": {"provider": "nous"},
            "web": {"use_gateway": "false"},
        }
    )

    assert "web" in has_direct
    assert "web" not in already_managed
    assert set(unconfigured) == {"image_gen", "tts", "stt", "browser"}


# ---------------------------------------------------------------------------
# STT — managed-by-Nous detection (Phase 4 follow-up)
# ---------------------------------------------------------------------------

def test_stt_managed_by_nous_when_provider_openai_and_no_direct_key(monkeypatch):
    """Default `stt.provider: openai` with a Nous sub + no direct OpenAI key
    should route through the managed audio gateway."""
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "get_nous_auth_status", lambda: {"logged_in": True})
    monkeypatch.setattr(ns, "managed_nous_tools_enabled", lambda: True)
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: False)
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(
        ns,
        "is_managed_tool_gateway_ready",
        lambda vendor: vendor == "openai-audio",
    )

    features = ns.get_nous_subscription_features({"stt": {"provider": "openai"}})

    assert features.stt.available is True
    assert features.stt.active is True
    assert features.stt.managed_by_nous is True
    assert features.stt.direct_override is False
    assert features.stt.current_provider == "OpenAI Whisper"


def test_stt_direct_key_overrides_managed(monkeypatch):
    """When the user has VOICE_TOOLS_OPENAI_KEY set, STT should use the
    direct key, not the managed gateway — same precedence as TTS."""
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "get_nous_auth_status", lambda: {"logged_in": True})
    monkeypatch.setattr(ns, "managed_nous_tools_enabled", lambda: True)
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: False)
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "sk-direct-key")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(
        ns,
        "is_managed_tool_gateway_ready",
        lambda vendor: vendor == "openai-audio",
    )

    features = ns.get_nous_subscription_features({"stt": {"provider": "openai"}})

    assert features.stt.available is True
    assert features.stt.managed_by_nous is False
    assert features.stt.direct_override is True


def test_stt_groq_provider_requires_groq_key(monkeypatch):
    env = {"GROQ_API_KEY": "groq-key"}
    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(ns, "get_nous_auth_status", lambda: {})
    monkeypatch.setattr(ns, "managed_nous_tools_enabled", lambda: False)
    monkeypatch.setattr(ns, "_toolset_enabled", lambda config, key: False)
    monkeypatch.setattr(ns, "_has_agent_browser", lambda: False)
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "has_direct_modal_credentials", lambda: False)
    monkeypatch.setattr(ns, "is_managed_tool_gateway_ready", lambda vendor: False)

    features = ns.get_nous_subscription_features({"stt": {"provider": "groq"}})

    assert features.stt.available is True
    assert features.stt.managed_by_nous is False
    assert features.stt.current_provider == "Groq Whisper"
    assert features.stt.explicit_configured is True


def test_apply_nous_managed_defaults_flips_stt_provider_to_openai_for_nous_users(monkeypatch):
    """Fresh Nous-subscribed user with the DEFAULT_CONFIG `stt.provider: local`
    seed should have it auto-flipped to "openai" so the managed audio
    gateway transcribes their voice notes without needing faster-whisper
    installed."""
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    # CI installs [all] extras, so faster-whisper is importable there —
    # force the "no local backend" case this test is about.
    monkeypatch.setattr(ns, "_local_stt_backend_available", lambda: False)
    # Avoid the heavy real probing in get_nous_subscription_features.
    monkeypatch.setattr(
        ns,
        "get_nous_subscription_features",
        lambda config: ns.NousSubscriptionFeatures(
            subscribed=True,
            nous_auth_present=True,
            provider_is_nous=True,
            features={
                key: ns.NousFeatureState(
                    key=key, label=key, included_by_default=True,
                    available=False, active=False, managed_by_nous=False,
                    direct_override=False, toolset_enabled=False,
                    explicit_configured=False,
                )
                for key in ("web", "image_gen", "tts", "stt", "browser", "modal")
            },
        ),
    )

    config = {"stt": {"provider": "local"}}
    changed = ns.apply_nous_managed_defaults(config, enabled_toolsets=[])

    assert "stt" in changed
    assert config["stt"]["provider"] == "openai"


def _stt_features_stub(*, account_info):
    return ns.NousSubscriptionFeatures(
        subscribed=True,
        nous_auth_present=True,
        provider_is_nous=True,
        account_info=account_info,
        features={
            key: ns.NousFeatureState(
                key=key, label=key, included_by_default=True,
                available=False, active=False, managed_by_nous=False,
                direct_override=False, toolset_enabled=False,
                explicit_configured=False,
            )
            for key in ("web", "image_gen", "video_gen", "tts", "stt", "browser", "modal")
        },
    )


def test_apply_nous_managed_defaults_keeps_local_stt_when_backend_works(monkeypatch):
    """A working local backend (faster-whisper installed or custom command)
    is a strong intent signal — never flip it to the managed gateway."""
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "_local_stt_backend_available", lambda: True)
    monkeypatch.setattr(
        ns,
        "get_nous_subscription_features",
        lambda config, **kw: _stt_features_stub(
            account_info=_account(logged_in=True, paid=True)
        ),
    )

    config = {"stt": {"provider": "local"}}
    changed = ns.apply_nous_managed_defaults(config, enabled_toolsets=[])

    assert "stt" not in changed
    assert config["stt"]["provider"] == "local"


def test_apply_nous_managed_defaults_skips_stt_when_not_entitled(monkeypatch):
    """A subscriber whose tool pool doesn't cover openai-audio must not be
    pointed at a managed gateway that will refuse them."""
    monkeypatch.setattr(ns, "get_env_value", lambda name: "")
    monkeypatch.setattr(ns, "resolve_openai_audio_api_key", lambda: "")
    monkeypatch.setattr(ns, "_local_stt_backend_available", lambda: False)
    monkeypatch.setattr(
        ns,
        "get_nous_subscription_features",
        lambda config, **kw: _stt_features_stub(
            account_info=_account(logged_in=True, paid=False)
        ),
    )

    config = {"stt": {"provider": "local"}}
    changed = ns.apply_nous_managed_defaults(config, enabled_toolsets=[])

    assert "stt" not in changed
    assert config["stt"]["provider"] == "local"


def test_apply_nous_managed_defaults_skips_stt_when_groq_key_present(monkeypatch):
    """Don't override a user who explicitly set up Groq for STT."""
    env = {"GROQ_API_KEY": "groq-key"}
    monkeypatch.setattr(ns, "get_env_value", lambda name: env.get(name, ""))
    monkeypatch.setattr(ns, "managed_nous_tools_enabled", lambda: True)
    monkeypatch.setattr(
        ns,
        "get_nous_subscription_features",
        lambda config: ns.NousSubscriptionFeatures(
            subscribed=True,
            nous_auth_present=True,
            provider_is_nous=True,
            features={
                key: ns.NousFeatureState(
                    key=key, label=key, included_by_default=True,
                    available=False, active=False, managed_by_nous=False,
                    direct_override=False, toolset_enabled=False,
                    explicit_configured=False,
                )
                for key in ("web", "image_gen", "tts", "stt", "browser", "modal")
            },
        ),
    )

    config = {"stt": {"provider": "local"}}
    changed = ns.apply_nous_managed_defaults(config, enabled_toolsets=[])

    # STT was not flipped because the user has a Groq key configured.
    assert "stt" not in changed
    assert config["stt"]["provider"] == "local"


def test_apply_gateway_defaults_sets_stt_use_gateway(monkeypatch):
    config = {}
    changed = ns.apply_gateway_defaults(config, ["stt"])

    assert "stt" in changed
    assert config["stt"]["provider"] == "openai"
    assert config["stt"]["use_gateway"] is True
