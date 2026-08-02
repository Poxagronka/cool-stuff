"""URL canonicalisation and dedup keys.

Order matters: unwrap redirect params, rfc-normalise, strip trackers, apply
site rules, and only then sort query params.
"""

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "ga_", "hsa_", "vero_", "_hs")

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "twclid",
    "igshid", "igsh", "mc_cid", "mc_eid", "yclid", "ysclid", "_openstat",
    "ref", "ref_src", "ref_url", "referrer", "source", "spm", "scm",
    "aff_platform", "aff_trace_key", "sk", "si", "feature", "share",
    "share_id", "trk", "trkCampaign", "originalSubdomain", "rdt",
    "campaign", "campaignid", "adgroupid", "wickedid", "cid", "srsltid",
}

# params carrying the real destination inside a wrapper url
REDIRECT_PARAMS = ("url", "u", "target", "dest", "destination", "redirect", "q", "to")

DEFAULT_PORTS = {"http": "80", "https": "443"}

_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)
_ALI_ITEM = re.compile(r"/item/(?:[^/]*?)(\d{6,})\.html", re.I)


def _strip_tracking(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        (k, v)
        for k, v in pairs
        if k.lower() not in TRACKING_PARAMS
        and not k.lower().startswith(TRACKING_PREFIXES)
    ]


def unwrap(url: str, depth: int = 3) -> str:
    """Pull the real url out of a redirect wrapper, offline."""
    for _ in range(depth):
        parts = urlsplit(url)
        pairs = dict(parse_qsl(parts.query, keep_blank_values=True))
        for key in REDIRECT_PARAMS:
            candidate = pairs.get(key, "")
            if candidate.startswith(("http://", "https://")):
                url = unquote(candidate)
                break
            if candidate.startswith("http%3A") or candidate.startswith("https%3A"):
                url = unquote(candidate)
                break
        else:
            return url
    return url


def site_rules(host: str, path: str, query: str) -> tuple[str, str, str]:
    """Reduce (host, path, query) to whatever actually identifies the resource."""
    if "amazon." in host:
        m = _AMAZON_ASIN.search(path)
        if m:
            return host, f"/dp/{m.group(1).upper()}", ""
    if "aliexpress." in host:
        m = _ALI_ITEM.search(path)
        if m:
            return host, f"/item/{m.group(1)}.html", ""
    if host == "youtu.be":
        vid = path.lstrip("/").split("/")[0]
        if vid:
            return "youtube.com", "/watch", urlencode({"v": vid})
    if host == "youtube.com":
        vid = dict(parse_qsl(query)).get("v")
        if vid:
            return host, "/watch", urlencode({"v": vid})
    return host, path, query


def normalise(raw: str) -> str:
    """Canonical form of a url. Deterministic, no network."""
    url = unwrap(raw.strip())
    parts = urlsplit(url)

    scheme = (parts.scheme or "https").lower()
    host = parts.hostname or ""
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host in {"mobile.twitter.com", "twitter.com"}:
        host = "x.com"
    if host in {"m.youtube.com", "music.youtube.com"}:
        host = "youtube.com"

    host, path, query = site_rules(host, parts.path, parts.query)

    port = parts.port
    netloc = host
    if port and str(port) != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    pairs = _strip_tracking(parse_qsl(query, keep_blank_values=True))
    pairs.sort()

    # fragments are client-side only, except spa hashbang routes
    fragment = parts.fragment if parts.fragment.startswith("!") else ""

    return urlunsplit((scheme, netloc, path, urlencode(pairs), fragment))


def key(url: str) -> str:
    """Dedup key: normalised url without scheme."""
    parts = urlsplit(normalise(url))
    return urlunsplit(("", parts.netloc, parts.path, parts.query, parts.fragment)).lstrip("/")


def domain(url: str) -> str:
    host = (urlsplit(normalise(url)).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_bare_root(url: str) -> bool:
    """A resolved url that is just a domain root means the link died.

    Dead affiliate shorteners redirect to the shop homepage rather than
    returning 404, so without this every dead link collapses into one record.
    """
    parts = urlsplit(url)
    return parts.path in ("", "/") and not parts.query
