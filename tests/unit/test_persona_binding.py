"""Persona binding: prompt precedence, parameter merging, per-call params."""

from modules.chat.facade import _build_prompt, _generate
from modules.llm.persona import ResolvedPersona, merge_params, normalize_persona_id


def _persona(prompt="persona prompt", **params):
    base = {"temperature": 0.5, "max_tokens": 256, "top_p": 0.8, "repetition_penalty": 1.2}
    base.update(params)
    return ResolvedPersona(id="anna", name="Анна", system_prompt=prompt, params=base)


class _LLM:
    """Minimal stand-in for a persona-aware LLM service."""

    def __init__(self, service_prompt="service prompt"):
        self._prompt = service_prompt
        self.calls = []

    def get_system_prompt(self):
        return self._prompt

    def generate_response_from_messages(self, messages, stream=False, tools=None, params=None):
        self.calls.append({"stream": stream, "tools": tools, "params": params})
        return "ok"


class _LegacyLLM:
    """Provider predating the persona feature — no `params` kwarg."""

    def __init__(self):
        self.calls = []

    def generate_response_from_messages(self, messages, stream=False, tools=None):
        self.calls.append({"stream": stream, "tools": tools})
        return "ok"


# --- normalize_persona_id ---------------------------------------------------


def test_normalize_treats_blank_and_sentinels_as_no_persona():
    for value in ("", "   ", "none", "NONE", "null", None, 42):
        assert normalize_persona_id(value) is None


def test_normalize_strips_whitespace():
    assert normalize_persona_id("  anna  ") == "anna"


# --- merge_params -----------------------------------------------------------


def test_persona_params_are_used_when_no_explicit_params():
    assert merge_params(None, _persona()) == {
        "temperature": 0.5,
        "max_tokens": 256,
        "top_p": 0.8,
        "repetition_penalty": 1.2,
    }


def test_explicit_params_win_over_persona():
    merged = merge_params({"temperature": 0.9}, _persona())
    assert merged["temperature"] == 0.9
    assert merged["max_tokens"] == 256  # persona value survives


def test_unknown_keys_are_dropped_and_no_persona_means_no_params():
    assert merge_params({"nonsense": 1}, None) == {}
    assert merge_params(None, None) == {}


# --- prompt precedence ------------------------------------------------------


def test_explicit_prompt_beats_everything():
    prompt = _build_prompt("explicit", {"system_prompt": "session"}, _persona(), _LLM())
    assert prompt == "explicit"


def test_session_prompt_beats_persona():
    prompt = _build_prompt(None, {"system_prompt": "session"}, _persona(), _LLM())
    assert prompt == "session"


def test_persona_fills_the_slot_when_session_prompt_is_empty():
    prompt = _build_prompt(None, {"system_prompt": ""}, _persona(), _LLM())
    assert prompt == "persona prompt"


def test_service_prompt_is_the_last_resort_without_a_persona(monkeypatch):
    monkeypatch.setattr("modules.chat.facade._load_platform_agent_prompt", lambda: None)
    prompt = _build_prompt(None, {}, None, _LLM())
    assert prompt == "service prompt"


def test_platform_agent_sits_between_persona_and_service(monkeypatch):
    monkeypatch.setattr("modules.chat.facade._load_platform_agent_prompt", lambda: "platform")
    assert _build_prompt(None, {}, None, _LLM()) == "platform"
    assert _build_prompt(None, {}, _persona(), _LLM()) == "persona prompt"


# --- per-call params --------------------------------------------------------


def test_params_reach_a_persona_aware_service():
    llm = _LLM()
    _generate(llm, [], stream=True, params={"temperature": 0.3})
    assert llm.calls[0]["params"] == {"temperature": 0.3}


def test_params_are_dropped_for_a_legacy_service():
    llm = _LegacyLLM()
    _generate(llm, [], stream=False, params={"temperature": 0.3})
    assert llm.calls == [{"stream": False, "tools": None}]


def test_empty_params_are_not_passed():
    llm = _LLM()
    _generate(llm, [], stream=False, params={})
    assert llm.calls[0]["params"] is None
