"""Optional Google Search discovery. Returned URLs are candidates, not evidence."""
import os
from urllib.parse import urlsplit

import requests

# Exact, independently maintained hosts only; expand only after verification.
SOURCE_HOSTS = frozenset({'health.ec.europa.eu', 'www.bsigroup.com', 'www.tuvsud.com', 'www.tuv.com'})
_request_count = 0


class GroundedDiscoveryError(RuntimeError):
    """Discovery failed or could not establish that Google Search ran."""


def _host(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        return p.hostname
    except (TypeError, ValueError):
        return None


def _generate(query, api_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        return client.models.generate_content(model='gemini-2.5-flash', contents=query,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    finally:
        client.close()


def discover_links(query, *, api_key=None, generate=None):
    """Return only grounded, allowlisted source URLs; never model text.

    Empty results do not mean discovery is exhaustive. Raises on failed or
    ungrounded searches. The caller must independently retrieve and verify sources.
    """
    key = api_key or os.environ.get('GEMINI_API_KEY')
    if not key:
        raise GroundedDiscoveryError('GEMINI_API_KEY is not configured')
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise GroundedDiscoveryError('Invalid discovery query')
    if generate is None:
        global _request_count
        try:
            limit = max(0, min(int(os.environ.get('REVISION_SEARCH_MAX_PER_RUN', '5')), 20))
        except ValueError:
            raise GroundedDiscoveryError('Invalid search budget') from None
        if _request_count >= limit:
            raise GroundedDiscoveryError('Search budget exhausted')
        _request_count += 1
    try:
        response = generate(query) if generate else _generate(query, key)
    except Exception:
        raise GroundedDiscoveryError('Google Search request failed') from None
    candidates = getattr(response, 'candidates', None) or []
    metadata = getattr(candidates[0], 'grounding_metadata', None) if candidates else None
    if not metadata or not getattr(metadata, 'web_search_queries', None) or not getattr(metadata, 'grounding_chunks', None):
        raise GroundedDiscoveryError('Google Search returned no grounding metadata or source links')
    links = []
    for chunk in metadata.grounding_chunks[:8]:
        uri = getattr(getattr(chunk, 'web', None), 'uri', None)
        if (_host(uri) == 'vertexaisearch.cloud.google.com'
                and urlsplit(uri).path.startswith('/grounding-api-redirect/')):
            try:
                response = requests.get(uri, allow_redirects=False, timeout=4, stream=True)
                try:
                    if response.status_code not in (301, 302, 303, 307, 308):
                        raise GroundedDiscoveryError('Google grounding redirect did not resolve')
                    uri = response.headers.get('Location')
                    if not uri:
                        raise GroundedDiscoveryError('Google grounding redirect missing Location')
                finally:
                    close = getattr(response, 'close', None)
                    if close:
                        close()
            except requests.RequestException:
                raise GroundedDiscoveryError('Google grounding redirect request failed') from None
        if _host(uri) in SOURCE_HOSTS and uri not in links:
            links.append(uri)
    return links
