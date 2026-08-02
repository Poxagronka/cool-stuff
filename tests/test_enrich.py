"""The ssrf guard on the fetch side, driven offline.

Nothing here talks to the network: literal addresses need no dns, and the one
hostname that appears has its resolution stubbed.
"""

import asyncio
import ipaddress

import httpx
import pytest

from tglinks import enrich

PRIVATE = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8443/admin",
    "http://[::1]/admin",
    "http://[::ffff:127.0.0.1]/admin",
    "http://192.168.1.14/router",
    "http://10.0.0.5:9200/_cat/indices",
    "http://169.254.169.254/latest/meta-data/",
    "http://[fd00::1]/",
    "http://0.0.0.0:8000/",
]

NOT_HTTP = [
    "file:///etc/passwd",
    "ftp://192.0.2.10/pub",
    "gopher://192.0.2.10:70/_x",
    "data:text/html,<title>hi</title>",
]


def run(coro):
    return asyncio.run(coro)


def guarded_client(handler):
    """The client enrich builds, with the calls landing in handler instead."""
    return httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=enrich.MAX_HOPS,
        transport=enrich.GuardedTransport(httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize("url", PRIVATE)
def test_an_address_inside_the_network_is_refused(url):
    with pytest.raises(enrich.BlockedURL):
        run(enrich.check_url(url))


@pytest.mark.parametrize("url", NOT_HTTP)
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(enrich.BlockedURL):
        run(enrich.check_url(url))


def test_a_public_address_goes_through():
    run(enrich.check_url("http://93.184.216.34/index.html"))


def test_nothing_reaches_a_private_target():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="<html></html>")

    async def go():
        async with guarded_client(handler) as client:
            return await client.get("http://127.0.0.1:8443/admin")

    with pytest.raises(enrich.BlockedURL):
        run(go())
    assert seen == []


def stub_dns(monkeypatch, table):
    async def fake(host):
        # a literal address resolves to itself, same as getaddrinfo would
        return [ipaddress.ip_address(addr) for addr in table.get(host, [host])]

    monkeypatch.setattr(enrich, "_resolve", fake)


def test_a_hostname_pointing_at_loopback_is_refused(monkeypatch):
    stub_dns(monkeypatch, {"lab.example.com": ["127.0.0.1"]})
    with pytest.raises(enrich.BlockedURL):
        run(enrich.check_url("https://lab.example.com/admin"))


def test_a_public_host_cannot_redirect_into_the_network(monkeypatch):
    stub_dns(monkeypatch, {"short.example.com": ["93.184.216.34"]})
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})

    async def go():
        async with guarded_client(handler) as client:
            return await client.get("https://short.example.com/x")

    with pytest.raises(enrich.BlockedURL):
        run(go())
    # the first hop was allowed, the metadata service was never asked
    assert seen == ["https://short.example.com/x"]


def test_a_redirect_between_public_hosts_still_works(monkeypatch):
    stub_dns(monkeypatch, {
        "short.example.com": ["93.184.216.34"],
        "arcteryx.example.com": ["93.184.216.35"],
    })

    def handler(request):
        if request.url.host == "short.example.com":
            return httpx.Response(302, headers={"location": "https://arcteryx.example.com/beta"})
        return httpx.Response(200, text="<html><title>Beta LT</title></html>")

    async def go():
        async with guarded_client(handler) as client:
            return await client.get("https://short.example.com/x")

    assert "Beta LT" in run(go()).text


def test_a_blocked_link_degrades_like_a_dead_one():
    """enrich must hand back the same empty Meta an unreachable url gives."""
    meta = run(enrich.enrich("http://127.0.0.1:8443/admin"))
    assert not meta.ok()
    assert meta.http_status == 0
    assert meta.url == "http://127.0.0.1:8443/admin"
