# MDCG predecessor discovery

When grounding fails (including a missing API key, quota error, ungrounded response or request failure), the MDCG predecessor adapter falls back to the European Commission's public search at `https://ec.europa.eu/search/`. It searches by document number, follows at most four exact-host `health.ec.europa.eu/latest-updates/` result pages whose titles match the immediate predecessor, and collects at most eight issuer `/document/download/` links. It checks robots.txt, refuses redirects, caps response sizes, and applies network timeouts. Each candidate must still pass the existing independent PDF download, robots, header identity, revision and appendix checks before it can be compared. A previous update page can point to a PDF overwritten with the current revision; such a candidate is rejected. Other agencies and appendix discovery are not supported by this fallback. Search pagination is not traversed and no result or a capped search is never proof of absence. If both searches fail, discovery is unavailable. A successful fallback with no candidates is non-exhaustive.

Live check for MDCG 2020-16 rev.5 found the issuer's rev.4 update page and its linked PDF, but the PDF had been overwritten with rev.5 and was rejected. This verifies discovery and rejection, not a successful live predecessor comparison.

## Optional Google Search candidate discovery

`collectors.grounded_discovery.discover_links(query)` uses the existing `GEMINI_API_KEY`; the MDCG collector invokes it only when it cannot find explicit revision history or an immediately preceding version in the official catalogue. Search runs only where the key is configured. `REVISION_SEARCH_MAX_PER_RUN` limits requests per process (default 5, maximum 20); exhausted budgets are reported as incomplete, not as no changes. It calls the official `google-genai` SDK with the `google_search` tool and returns only source URLs from grounding metadata. For example, from the project root:

```python
from collectors.grounded_discovery import discover_links, GroundedDiscoveryError

try:
    links = discover_links('MDCG 2020-16 previous revision European Commission')
except GroundedDiscoveryError as error:
    print('Discovery failed:', error)
else:
    for link in links:
        print(link)
```

The result contains at most the first eight grounding chunks and only exact allowlisted HTTPS hosts: `health.ec.europa.eu`, `www.bsigroup.com`, `www.tuvsud.com`, and `www.tuv.com`. BSI and TÜV hosts are independent notified-body sources, not the MDCG issuer. A recognized Google grounding redirect is requested without following redirects; its Location is accepted only if it is already an allowlisted source URL. Other source redirects are not followed. Google request timeout is 20 seconds (one SDK attempt); each of at most eight redirect requests has a four-second network timeout. These are network timeouts, not a hard wall-clock deadline. Failures are explicit and sanitized; missing grounding metadata is an error.

This is discovery only: neither URL, search result, model output nor an independently maintained notified-body site is proof of an issuer revision or of a change. Retrieve a source independently, safely check redirects and source identity, and verify its content before use. A successful search, an empty filtered result, or the eight-result limit **does not establish exhaustive issuer-site discovery** and must not be used to mark a prior version absent. No model-generated text or snippet is returned. The current implementation supports predecessor discovery for MDCG; it does not yet use notified-body explanations.

Google's [grounding documentation](https://ai.google.dev/gemini-api/docs/generate-content/google-search) specifies `google_search` and `groundingMetadata.groundingChunks`. SDK request serialization was tested offline using `google-genai` 2.34.0 and a mock HTTP transport; no authenticated Google Search has been tested locally. Actual redirect behavior, quotas, model availability, credentials and the project's account-specific billing remain unverified.

According to [Google's pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash), Gemini 2.5 Flash paid-tier grounding includes 1,500 free grounded prompts per day shared with Flash-Lite, then $35 per 1,000 grounded prompts; token charges also apply. Free-tier limits and availability differ, pricing can change, and actual costs depend on usage and account terms. Each MDCG revision without an explicit history or catalogue predecessor can make a grounded request, including scheduled runs, within the per-process budget above.
