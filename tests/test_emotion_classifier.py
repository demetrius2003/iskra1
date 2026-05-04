"""Lexicon emotion classifier."""

from pathlib import Path

import pytest

from iskra.core.emotion_classifier import EmotionClassifier

_LEX = Path(__file__).resolve().parent.parent / "emotion_lexicon.yaml"


@pytest.fixture
def classifier() -> EmotionClassifier:
    return EmotionClassifier.from_yaml_file(_LEX)


def test_classify_positive_russian(classifier: EmotionClassifier) -> None:
    v, a = classifier.classify("я чувствую радость и надежду сегодня")
    assert v > 0.2
    assert 0.0 <= a <= 1.0


def test_classify_negative_and_arousal(classifier: EmotionClassifier) -> None:
    v, a = classifier.classify("страх!!! ПАНИКА ужас")
    assert v < -0.05
    assert a > 0.45


def test_empty_lexicon_neutral() -> None:
    c = EmotionClassifier(positive=set(), negative=set(), high_arousal=set())
    v, _a = c.classify("просто текст без маркеров")
    assert abs(v) < 0.15


def test_lexicon_merge_custom_file() -> None:
    stub = Path(__file__).resolve().parent / "emotion_lexicon_custom_stub.yaml"
    plain = EmotionClassifier.from_yaml_file(_LEX)
    merged = EmotionClassifier.from_lexicon_sources(_LEX, lexicon_custom_file=stub)
    assert merged.lexicon_counts()["positive_words"] > plain.lexicon_counts()["positive_words"]
    v, _a = merged.classify("допслово")
    assert v > 0.05


def test_classify_max_chars_truncates_prefix() -> None:
    c = EmotionClassifier.from_yaml_file(_LEX)
    suffix = " радость счастье надежда"
    long = ("z" * 200) + suffix
    v_full, _ = c.classify(long)
    v_trunc, _ = c.classify(long, max_chars=80)
    assert v_full > 0.12
    assert v_trunc < v_full - 0.03


def test_emotion_classifier_config_max_chars_validation() -> None:
    from pydantic import ValidationError

    from iskra.core.config import EmotionClassifierConfig

    EmotionClassifierConfig(max_input_chars=None)
    with pytest.raises(ValidationError):
        EmotionClassifierConfig(max_input_chars=12)
