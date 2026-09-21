"""Web origins allowed to call the read-only TripLens analysis API."""

DEFAULT_WEB_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://triplens-web-preview.vercel.app",
    # Current operator-facing Preview deployment used for review.
    "https://triplens-web-preview-pvb6ms2t5-junsic-s-projects.vercel.app",
    "https://triplens-web-preview-git-codex-analysi-cb9b23-junsic-s-projects.vercel.app",
)


def web_origins(configured: str = "") -> list[str]:
    """Return deterministic defaults plus one optional configured origin."""
    origins = list(DEFAULT_WEB_ORIGINS)
    value = configured.strip()
    if value and value not in origins:
        origins.append(value)
    return origins
