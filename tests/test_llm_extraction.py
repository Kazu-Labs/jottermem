from jottermem.extraction import LLMExtractor


def test_parses_plain_lines():
    extractor = LLMExtractor(complete=lambda prompt: "Lives in Boston.\nWorks at Acme Corp.")
    assert extractor.extract("I live in Boston and work at Acme Corp.") == [
        "Lives in Boston.",
        "Works at Acme Corp.",
    ]


def test_strips_bullets_and_numbering():
    extractor = LLMExtractor(
        complete=lambda prompt: "- Likes tea\n* Likes coffee\n1. Works remotely\n2) Lives in Seattle"
    )
    assert extractor.extract("some text") == [
        "Likes tea",
        "Likes coffee",
        "Works remotely",
        "Lives in Seattle",
    ]


def test_empty_response_yields_no_facts():
    extractor = LLMExtractor(complete=lambda prompt: "")
    assert extractor.extract("just chit-chat, nothing to remember") == []


def test_empty_input_never_calls_complete():
    calls = []
    extractor = LLMExtractor(complete=lambda prompt: calls.append(prompt) or "")
    assert extractor.extract("   ") == []
    assert calls == []


def test_prompt_includes_input_text():
    captured = {}

    def complete(prompt):
        captured["prompt"] = prompt
        return "a fact"

    extractor = LLMExtractor(complete=complete)
    extractor.extract("raw input text")
    assert "raw input text" in captured["prompt"]
