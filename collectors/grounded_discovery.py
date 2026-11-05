"""Google Search grounding is permanently disabled for revision discovery."""


class GroundedDiscoveryError(RuntimeError):
    """Raised because paid grounding discovery is disabled."""


def discover_links(query, *, api_key=None, generate=None):
    """Disabled regardless of credentials or injected generators."""
    raise GroundedDiscoveryError('Google grounding is disabled')
