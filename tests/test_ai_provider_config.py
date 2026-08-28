from config import settings
from app.services.ai_service import get_ai_status


def test_ai_provider_defaults_are_configurable():
    assert hasattr(settings, "ai_provider")
    assert hasattr(settings, "ai_model")
    assert isinstance(settings.ai_provider, str)
    assert settings.ai_provider.lower() in {"ollama", "openrouter", "google_ai_studio"}

    status = get_ai_status()
    assert "provider" in status
    assert "model" in status
    assert status["provider"] in {"ollama", "openrouter", "google_ai_studio", "disabled"}
