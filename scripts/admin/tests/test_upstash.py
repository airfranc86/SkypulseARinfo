from __future__ import annotations

from urllib.parse import urlparse

from fakes import (
    ALL_SECRETS,
    TEST_TOKEN,
    TEST_UPSTASH_URL,
    FakeHttp,
    failure,
    json_result,
    text_result,
)
from monitor_core.upstash import UpstashReader

KEY = "skypulse:open_meteo:counter:2026-10-05"


def _reader(response) -> tuple[UpstashReader, FakeHttp]:
    http = FakeHttp([("/get/", response)])
    return UpstashReader(http, TEST_UPSTASH_URL, TEST_TOKEN), http


def test_reads_with_the_get_command_only() -> None:
    reader, http = _reader(json_result({"result": "123"}))
    reading = reader.read_counter(KEY)
    assert reading.count == 123 and reading.present and reading.error is None
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call.url == f"{TEST_UPSTASH_URL}/get/{KEY}"
    assert call.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
    assert urlparse(call.url).path.startswith("/get/")


def test_only_read_commands_are_ever_built() -> None:
    reader, http = _reader(json_result({"result": "1"}))
    for service in ("open_meteo", "checkwx", "smn_alertas", "metar_awc"):
        reader.read_counter(f"skypulse:{service}:counter:2026-10-05")
    commands = {urlparse(c.url).path.split("/")[1].lower() for c in http.calls}
    assert commands == {"get"}


def test_trailing_slash_in_base_url_is_normalised() -> None:
    http = FakeHttp([("/get/", json_result({"result": "1"}))])
    UpstashReader(http, TEST_UPSTASH_URL + "/", TEST_TOKEN).read_counter(KEY)
    assert http.calls[0].url == f"{TEST_UPSTASH_URL}/get/{KEY}"


def test_missing_key_reads_as_zero_not_error() -> None:
    reader, _ = _reader(json_result({"result": None}))
    reading = reader.read_counter(KEY)
    assert (reading.count, reading.present, reading.error) == (0, False, None)


def test_http_error_is_reported_without_secrets() -> None:
    reader, _ = _reader(json_result({"error": f"bad token {TEST_TOKEN}"}, status=401))
    reading = reader.read_counter(KEY)
    assert reading.error is not None and "401" in reading.error
    assert not any(secret in reading.error for secret in ALL_SECRETS)


def test_transport_failure_is_reported_without_secrets() -> None:
    reader, _ = _reader(failure(error="TimeoutError"))
    reading = reader.read_counter(KEY)
    assert reading.error is not None and "sin respuesta" in reading.error
    assert reading.count == 0 and not reading.present
    assert not any(secret in reading.error for secret in ALL_SECRETS)


def test_unexpected_result_type_is_an_error() -> None:
    reader, _ = _reader(json_result({"result": "no-es-un-numero"}))
    reading = reader.read_counter(KEY)
    assert reading.error is not None and "inesperada" in reading.error


def test_invalid_json_is_an_error() -> None:
    reader, _ = _reader(text_result("<html>nope</html>"))
    assert reader.read_counter(KEY).error is not None


def test_error_envelope_with_200_is_an_error() -> None:
    reader, _ = _reader(json_result({"error": "ERR something"}))
    assert reader.read_counter(KEY).error is not None


def test_exception_raised_by_the_client_never_leaks_its_message() -> None:
    http = FakeHttp([("/get/", RuntimeError(f"boom {TEST_TOKEN} {TEST_UPSTASH_URL}"))])
    reading = UpstashReader(http, TEST_UPSTASH_URL, TEST_TOKEN).read_counter(KEY)
    assert reading.error is not None
    assert "RuntimeError" in reading.error
    assert not any(secret in reading.error for secret in ALL_SECRETS)


def test_reader_repr_hides_credentials() -> None:
    reader, _ = _reader(json_result({"result": "1"}))
    assert not any(secret in repr(reader) for secret in ALL_SECRETS)
