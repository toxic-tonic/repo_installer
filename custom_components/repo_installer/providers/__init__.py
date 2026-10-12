"""Provider adapters and auto-detection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp
from yarl import URL

from ..const import (
    DETECT_REQUEST_TIMEOUT,
    DETECT_TOTAL_TIMEOUT,
    PROVIDER_AUTO,
    PROVIDER_GITEA,
    PROVIDER_GITHUB,
    PROVIDER_GITLAB,
)
from .base import (
    Provider,
    RateLimitError,
    Release,
    RepoAuthError,
    RepoConnectionError,
    RepoError,
    RepoLocation,
    RepoNotFoundError,
)
from .gitea import GiteaProvider
from .github import GITHUB_HOST, GitHubProvider
from .gitlab import GITLAB_HOST, GitLabProvider

__all__ = [
    "PROVIDERS",
    "DetectionError",
    "Provider",
    "RateLimitError",
    "Release",
    "RepoAuthError",
    "RepoConnectionError",
    "RepoError",
    "RepoLocation",
    "RepoNotFoundError",
    "async_detect",
    "build_provider",
    "parse_repo_url",
]

# Order = priority when several candidates answer validly.
PROVIDERS: dict[str, type[Provider]] = {
    PROVIDER_GITEA: GiteaProvider,
    PROVIDER_GITLAB: GitLabProvider,
    PROVIDER_GITHUB: GitHubProvider,
}

MAX_GITLAB_SPLITS = 4


class DetectionError(RepoError):
    """Detection failed; `reason` is a config flow error key."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RepoUrl:
    """A normalized repository URL split into path segments."""

    url: URL  # scheme://host[:port]/seg/…, no query, no trailing slash
    segments: tuple[str, ...]

    def location(self, base_len: int) -> RepoLocation:
        base_path = "/".join(self.segments[:base_len])
        base = self.url.with_path(f"/{base_path}" if base_path else "")
        return RepoLocation(base, "/".join(self.segments[base_len:]))


def parse_repo_url(text: str) -> RepoUrl:
    """Parse e.g. http://host:3000/sub/owner/repo(.git); ValueError if unusable."""
    url = URL(text.strip())
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError("not an http(s) URL")
    segments = [s for s in url.path.split("/") if s]
    if "-" in segments:  # GitLab web UI paths: …/project/-/releases
        segments = segments[: segments.index("-")]
    if segments and segments[-1].lower().endswith(".git"):
        segments[-1] = segments[-1][:-4]
    if len(segments) < 2 or not all(segments):
        raise ValueError("URL must contain owner/repository")
    normalized = url.with_path("/" + "/".join(segments)).with_query(None).with_fragment(None)
    return RepoUrl(normalized, tuple(segments))


def build_provider(
    session: aiohttp.ClientSession, key: str, location: RepoLocation, token: str | None
) -> Provider:
    return PROVIDERS[key](session, location, token)


def _candidates(
    session: aiohttp.ClientSession, repo_url: RepoUrl, token: str | None, wanted: str
) -> list[Provider]:
    """Possible (provider, location) pairs, in priority order."""
    host = (repo_url.url.host or "").lower()
    n = len(repo_url.segments)
    if wanted == PROVIDER_AUTO:
        if host == GITHUB_HOST:
            wanted = PROVIDER_GITHUB
        elif host == GITLAB_HOST:
            wanted = PROVIDER_GITLAB
    keys = list(PROVIDERS) if wanted == PROVIDER_AUTO else [wanted]
    result: list[Provider] = []
    for key in keys:
        if key == PROVIDER_GITLAB:
            if host == GITLAB_HOST:
                splits = [0]
            else:
                # Nested groups vs. sub path are ambiguous: try shortest base first
                splits = list(range(0, n - 1))[:MAX_GITLAB_SPLITS]
        elif key == PROVIDER_GITHUB and host == GITHUB_HOST:
            if n != 2:
                continue
            splits = [0]
        else:
            splits = [n - 2]  # owner/repo are the last two segments
        result.extend(
            build_provider(session, key, repo_url.location(i), token) for i in splits
        )
    return result


async def async_detect(
    session: aiohttp.ClientSession,
    repo_url: RepoUrl,
    token: str | None,
    wanted: str = PROVIDER_AUTO,
) -> Provider:
    """Probe all candidates concurrently, return the first valid in priority order.

    Bounded by DETECT_TOTAL_TIMEOUT. Raises DetectionError with a flow error key.
    """
    candidates = _candidates(session, repo_url, token, wanted)
    if not candidates:
        raise DetectionError("no_compatible_git", "no candidate for this URL")

    async def probe(provider: Provider) -> BaseException | None:
        try:
            await provider.async_probe(timeout=DETECT_REQUEST_TIMEOUT)
        except RepoError as err:
            return err
        return None

    tasks = [asyncio.ensure_future(probe(p)) for p in candidates]
    try:
        async with asyncio.timeout(DETECT_TOTAL_TIMEOUT):
            # Walk in priority order; stop at the first success without waiting
            # for lower-priority probes. asyncio.wait does not cancel on timeout.
            for provider, task in zip(candidates, tasks, strict=True):
                await asyncio.wait({task})
                if task.result() is None:
                    return provider
    except TimeoutError:
        pass
    finally:
        for task in tasks:
            task.cancel()
    outcomes = [
        t.result() if t.done() and not t.cancelled() else RepoConnectionError("timeout")
        for t in tasks
    ]

    forced = wanted != PROVIDER_AUTO
    if any(isinstance(o, RateLimitError) for o in outcomes):
        raise DetectionError("rate_limited", "rate limit reached")
    if token and any(isinstance(o, RepoAuthError) for o in outcomes):
        raise DetectionError("invalid_auth", "token rejected")
    if all(isinstance(o, RepoConnectionError) for o in outcomes):
        raise DetectionError("cannot_connect", "host not reachable or timed out")
    if forced:
        raise DetectionError("provider_mismatch", f"{PROVIDERS[wanted].name} did not answer")
    raise DetectionError("no_compatible_git", "no compatible Git detected")
