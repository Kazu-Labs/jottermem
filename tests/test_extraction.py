from jottermem.extraction import SentenceExtractor


def test_splits_multiple_sentences():
    extractor = SentenceExtractor()
    facts = extractor.extract("I live in Boston. I work at Acme Corp. I like tea.")
    assert facts == ["I live in Boston.", "I work at Acme Corp.", "I like tea."]


def test_strips_whitespace_and_filters_short_fragments():
    extractor = SentenceExtractor(min_length=4)
    facts = extractor.extract("  Hi.   A.  This is a real sentence.  ")
    assert facts == ["This is a real sentence."]


def test_empty_input():
    extractor = SentenceExtractor()
    assert extractor.extract("") == []
    assert extractor.extract("   ") == []


def test_single_sentence_no_trailing_punctuation():
    extractor = SentenceExtractor()
    assert extractor.extract("just one fact") == ["just one fact"]
