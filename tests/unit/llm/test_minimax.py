"""Unit tests for MiniMax provider support in decepticon.llm.models"""


from decepticon.llm.factory import LLMFactory
from decepticon.llm.models import (
    MINIMAX,
    MINIMAX_HIGHSPEED,
    LLMModelMapping,
    ModelAssignment,
    ProxyConfig,
)


class TestMinimaxModelConstants:
    def test_minimax_constant_format(self):
        assert MINIMAX == "minimax/MiniMax-M2.7"

    def test_minimax_highspeed_constant_format(self):
        assert MINIMAX_HIGHSPEED == "minimax/MiniMax-M2.7-highspeed"

    def test_minimax_uses_minimax_prefix(self):
        assert MINIMAX.startswith("minimax/")
        assert MINIMAX_HIGHSPEED.startswith("minimax/")


class TestMinimaxModelAssignment:
    def test_minimax_as_primary(self):
        assignment = ModelAssignment(primary=MINIMAX)
        assert assignment.primary == MINIMAX
        assert assignment.fallback is None

    def test_minimax_highspeed_as_fallback(self):
        assignment = ModelAssignment(primary=MINIMAX, fallback=MINIMAX_HIGHSPEED)
        assert assignment.fallback == MINIMAX_HIGHSPEED

    def test_minimax_temperature_default(self):
        assignment = ModelAssignment(primary=MINIMAX)
        assert assignment.temperature == 0.7

    def test_minimax_custom_temperature(self):
        assignment = ModelAssignment(primary=MINIMAX, temperature=1.0)
        assert assignment.temperature == 1.0


class TestMinimaxInMapping:
    def test_minimax_can_be_set_on_role(self):
        mapping = LLMModelMapping(
            recon=ModelAssignment(primary=MINIMAX, temperature=0.3)
        )
        assert mapping.get_assignment("recon").primary == MINIMAX

    def test_minimax_highspeed_can_be_fallback(self):
        mapping = LLMModelMapping(
            recon=ModelAssignment(primary=MINIMAX, fallback=MINIMAX_HIGHSPEED)
        )
        assert mapping.get_assignment("recon").fallback == MINIMAX_HIGHSPEED

    def test_minimax_factory_creates_model(self):
        proxy = ProxyConfig(url="http://localhost:4000", api_key="test-key")
        mapping = LLMModelMapping(
            recon=ModelAssignment(primary=MINIMAX, temperature=0.3)
        )
        factory = LLMFactory(proxy, mapping)
        model = factory.get_model("recon")
        assert model is not None
        assert model.model_name == MINIMAX

    def test_minimax_highspeed_factory_creates_model(self):
        proxy = ProxyConfig(url="http://localhost:4000", api_key="test-key")
        mapping = LLMModelMapping(
            recon=ModelAssignment(primary=MINIMAX_HIGHSPEED, temperature=0.3)
        )
        factory = LLMFactory(proxy, mapping)
        model = factory.get_model("recon")
        assert model.model_name == MINIMAX_HIGHSPEED

    def test_minimax_fallback_model_returned(self):
        proxy = ProxyConfig(url="http://localhost:4000", api_key="test-key")
        mapping = LLMModelMapping(
            recon=ModelAssignment(primary=MINIMAX, fallback=MINIMAX_HIGHSPEED)
        )
        factory = LLMFactory(proxy, mapping)
        fallbacks = factory.get_fallback_models("recon")
        assert len(fallbacks) == 1
        assert fallbacks[0].model_name == MINIMAX_HIGHSPEED
