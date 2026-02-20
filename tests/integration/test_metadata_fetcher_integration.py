"""
Integration tests for MetadataFetcher using real HTTP and curated test URLs.

Uses TEST_URLS from tests.test_data. Requires network. Run with:
  pytest tests/integration/test_metadata_fetcher_integration.py -m integration -v
"""
from __future__ import annotations

import random

import pytest

from tests.test_data import (
    TEST_URLS,
    TEST_URLS_COOKIES,
    TEST_URLS_ERROR_STATUS,
    TEST_URLS_SUCCESS,
)
from worker.app.config.settings import Settings
from worker.app.domain.metadata_fetcher import MetadataFetcher, MetadataFetchError
from worker.app.infrastructure.http.factory import create_http_client


@pytest.fixture
async def fetcher():
    """Real MetadataFetcher with real HTTP client; closed after test."""
    settings = Settings()
    client = create_http_client(settings)
    # Use a browser-like User-Agent so sites (e.g. Wikipedia) that block default clients return 2xx
    default_headers = {"User-Agent": "HTTP_Inventory-Test/1.0 (integration tests)"}
    f = MetadataFetcher(
        client,
        connect_timeout_seconds=settings.fetch_connect_timeout_seconds,
        read_timeout_seconds=settings.fetch_read_timeout_seconds,
        default_headers=default_headers,
    )
    yield f
    await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("url", TEST_URLS_SUCCESS, ids=lambda u: u.replace("https://", "").replace("http://", "")[:40])
async def test_fetcher_success_url_returns_metadata_result(fetcher, url):
    """Each success URL returns MetadataResult with headers dict, cookies, page_source str, status_code, final_url."""
    result = await fetcher.fetch(url)

    assert result is not None
    assert isinstance(result.headers, dict)
    assert isinstance(result.cookies, dict)
    assert isinstance(result.page_source, str)
    assert result.status_code >= 200 and result.status_code < 300
    assert result.final_url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetcher_success_headers_and_final_url(fetcher):
    """Redirect URL: final_url reflects resolution; headers present."""
    url = "https://httpbin.org/redirect/2"
    result = await fetcher.fetch(url)

    assert result.status_code == 200
    assert "httpbin.org" in result.final_url
    assert isinstance(result.headers, dict)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetcher_non_html_content_stored_in_page_source(fetcher):
    """Non-HTML (JSON, XML, image) body is stored in page_source as string."""
    # JSON
    r = await fetcher.fetch("https://httpbin.org/get")
    assert r.status_code == 200
    assert isinstance(r.page_source, str)
    assert "origin" in r.page_source or "url" in r.page_source or "headers" in r.page_source

    # XML
    r2 = await fetcher.fetch("https://httpbin.org/xml")
    assert r2.status_code == 200
    assert isinstance(r2.page_source, str)
    assert "slide" in r2.page_source or "item" in r2.page_source or "<" in r2.page_source


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("url,expected_status", TEST_URLS_ERROR_STATUS)
async def test_fetcher_error_status_raises(fetcher, url, expected_status):
    """4xx/5xx URLs cause MetadataFetchError (raise_for_status)."""
    with pytest.raises(MetadataFetchError):
        await fetcher.fetch(url)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("url", TEST_URLS_COOKIES, ids=lambda u: "cookies" if "cookies" in u else "session")
async def test_fetcher_cookie_urls_return_result(fetcher, url):
    """Cookie-set endpoints return 200 and result has cookies dict (may be empty from redirect)."""
    result = await fetcher.fetch(url)
    assert isinstance(result.headers, dict)
    assert isinstance(result.cookies, dict)
    assert result.status_code in (200, 302)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetcher_random_url_from_full_list(fetcher):
    """Pick a random URL from full TEST_URLS; either success or expected error."""
    url = random.choice(TEST_URLS)
    if "status/404" in url or "status/500" in url:
        with pytest.raises(MetadataFetchError):
            await fetcher.fetch(url)
    else:
        result = await fetcher.fetch(url)
        assert isinstance(result.headers, dict)
        assert isinstance(result.cookies, dict)
        assert isinstance(result.page_source, str)
        assert result.final_url
