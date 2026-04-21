"""LLM adapter wiring."""

from pathlib import Path

import pytest

from iskra.core.config import LLMConfig
from iskra.llm import create_llm_adapter
from iskra.llm.gigachat_adapter import GigaChatAdapter
from iskra.llm.yandexgpt_adapter import YandexGPTAdapter


def test_create_mock() -> None:
    cfg = LLMConfig(adapter="mock", settings={"mock": {"latency_ms": 1}})
    a = create_llm_adapter(cfg)
    assert a.is_available()


def test_gigachat_requires_credentials() -> None:
    cfg = LLMConfig()
    with pytest.raises(ValueError, match="gigachat"):
        GigaChatAdapter({}, cfg)


def test_gigachat_ca_bundle_must_exist(tmp_path: Path) -> None:
    cfg = LLMConfig()
    missing = tmp_path / "nope.cer"
    with pytest.raises(ValueError, match="ca_bundle_file"):
        GigaChatAdapter(
            {"credentials_base64": "eA==", "ca_bundle_file": str(missing)},
            cfg,
        )


def test_gigachat_ca_bundle_resolves_path(tmp_path: Path) -> None:
    cfg = LLMConfig()
    ca = tmp_path / "russian_trusted_root_ca.cer"
    ca.write_bytes(b"x")
    a = GigaChatAdapter({"credentials_base64": "eA==", "ca_bundle_file": str(ca)}, cfg)
    assert a._verify == str(ca.resolve())


def test_gigachat_verify_ssl_false_skips_ca_path(tmp_path: Path) -> None:
    cfg = LLMConfig()
    ca = tmp_path / "russian_trusted_root_ca.cer"
    ca.write_bytes(b"x")
    a = GigaChatAdapter(
        {
            "credentials_base64": "eA==",
            "ca_bundle_file": str(ca),
            "verify_ssl": False,
        },
        cfg,
    )
    assert a._verify is False


def test_yandex_requires_folder_or_uri() -> None:
    cfg = LLMConfig()
    with pytest.raises(ValueError, match="yandexgpt"):
        YandexGPTAdapter({}, cfg)


def test_yandex_model_uri_sets_folder() -> None:
    cfg = LLMConfig()
    a = YandexGPTAdapter(
        {"model_uri": "gpt://b1abc123/yandexgpt/latest", "auth": "iam", "iam_token": "x"},
        cfg,
    )
    assert a.is_available()
    assert a._folder_id == "b1abc123"
