"""Provider-neutral parts: errors, release model, HTTP with host binding.

Each adapter only knows its own API: where the repository and its releases
live, how a release maps onto `Release`, and which hosts may serve assets.
Download, SHA-256 check and redirect policy are shared and equally strict for
all providers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
from typing import Any, ClassVar

import aiohttp
from yarl import URL

from ..const import (
    API_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    MAX_ASSET_BYTES,
    MAX_REDIRECTS,
    SHA256_RE,
)
from ..version import looks_like_version

type Origin = tuple[str, str, int | None]


class RepoError(Exception):
    """Base error. Messages never contain the token."""


class RepoConnectionError(RepoError):
    """Host not reachable, timed out or answered with garbage."""


class RepoAuthError(RepoError):
    """Token rejected or required."""


class RepoNotFoundError(RepoError):
    """Repository or release not found."""


class RateLimitError(RepoError):
    """API rate limit reached (GitHub without token: 60 requests/hour)."""


class SchemaMismatchError(RepoError):
    """The host answered, but not like this provider's API."""


@dataclass(frozen=True)
class RepoLocation:
    """Where a repository lives: instance web root (incl. sub path) + repo path."""

    base_url: URL
    path: str  # owner/repo, GitLab also group/sub/project

    @property
    def web_url(self) -> URL:
        return URL(f"{str(self.base_url).rstrip('/')}/{self.path}")


@dataclass(frozen=True)
class Release:
    """The parts of a release the installer needs, identical for all providers."""

    version: str
    tag: str
    body: str
    html_url: str | None
    prerelease: bool
    asset_name: str | None = None
    asset_url: str | None = None
    sha256: str | None = None
    problem: str | None = None  # set when the release cannot be installed


@dataclass(frozen=True)
class ZipAsset:
    """A ZIP asset as listed by the provider."""

    name: str
    url: str
    sha256: str | None = None  # provider-side digest, if the API offers one (GitHub)


def select_zip(zips: list[ZipAsset], version: str, sha256: str | None) -> ZipAsset | None:
    """Pick the release ZIP.

    1. exactly one ZIP: that one
    2. else the only ZIP whose name contains the version (versioned name wins
       over a fixed name such as repo_installer.zip for HACS)
    3. else the only ZIP whose provider digest matches the SHA-256 of the notes
    """
    if len(zips) == 1:
        return zips[0]
    variants = {version, version.replace("+", "%2B")}
    versioned = [z for z in zips if any(v in z.name for v in variants)]
    if len(versioned) == 1:
        return versioned[0]
    if sha256:
        matching = [z for z in zips if z.sha256 and z.sha256.lower() == sha256]
        if len(matching) == 1:
            return matching[0]
    return None


def origin(url: URL) -> Origin:
    return (url.scheme, (url.host or "").lower(), url.port)


def release_version(name: str | None, tag: str) -> str:
    """Release title if it is a version (titles may carry '+', tags often can't)."""
    name = (name or "").strip()
    if name and looks_like_version(name):
        return name.removeprefix("v")
    return tag.strip().removeprefix("v")


class Provider:
    """One repository on one instance of one provider."""

    key: ClassVar[str]
    name: ClassVar[str]

    def __init__(
        self,
        session: aiohttp.ClientSession,
        location: RepoLocation,
        token: str | None = None,
    ) -> None:
        self._session = session
        self.location = location
        self._token = token or None

    # --- adapter interface -------------------------------------------------

    @property
    def repo_api_url(self) -> URL:
        """API URL of the repository itself (used to probe and validate)."""
        raise NotImplementedError

    def _auth_headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _api_accept(self) -> str:
        return "application/json"

    def _download_accept(self) -> str:
        return "application/octet-stream, */*"

    def _validate_repo(self, data: Any) -> None:
        """Raise SchemaMismatchError unless `data` describes exactly this repo."""
        raise NotImplementedError

    async def async_get_latest_release(self, include_prereleases: bool) -> Release:
        raise NotImplementedError

    def is_own_asset_url(self, url: str | URL) -> bool:
        """The asset link points into this repository on this instance."""
        raise NotImplementedError

    @property
    def download_origins(self) -> frozenset[Origin]:
        """Origins a download may be served from or redirected to."""
        return frozenset({origin(self.location.base_url)})

    @property
    def auth_origins(self) -> frozenset[Origin]:
        """Origins that receive the token. Object storage never does."""
        return frozenset({origin(self.location.base_url)})

    # --- shared ---------------------------------------------------------------

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _headers(self, accept: str, url: URL) -> dict[str, str]:
        headers = {"Accept": accept}
        if self._token and origin(url) in self.auth_origins:
            headers.update(self._auth_headers())
        return headers

    def _raise_for_status(self, resp: aiohttp.ClientResponse, what: str) -> None:
        if resp.status == 429:
            raise RateLimitError(f"Rate-Limit erreicht ({what})")
        if resp.status in (401, 403):
            raise RepoAuthError(f"HTTP {resp.status} for {what}")
        if resp.status == 404:
            raise RepoNotFoundError(f"HTTP 404 for {what}")
        if 300 <= resp.status < 400:
            # API redirects are not followed (token must not travel); renamed repos land here
            raise RepoNotFoundError(f"HTTP {resp.status} for {what}: moved, use the new URL")
        if resp.status != 200:
            raise RepoConnectionError(f"HTTP {resp.status} for {what}")

    async def _get_json(
        self,
        url: URL,
        params: dict[str, str] | None = None,
        timeout: float = API_TIMEOUT,
    ) -> Any:
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._headers(self._api_accept(), url),
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                self._raise_for_status(resp, str(url))
                try:
                    return await resp.json(content_type=None)
                except ValueError as err:
                    raise SchemaMismatchError(f"{url} did not answer with JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RepoConnectionError(self._scrub(f"{type(err).__name__}: {err}")) from err

    async def async_probe(self, timeout: float = API_TIMEOUT) -> None:
        """Check that this provider's API knows exactly this repository."""
        data = await self._get_json(self.repo_api_url, timeout=timeout)
        self._validate_repo(data)

    def _build_release(
        self,
        *,
        tag: str,
        name: str | None,
        body: str | None,
        html_url: str | None,
        prerelease: bool,
        zips: list[ZipAsset],
    ) -> Release:
        """Common checks: one selectable ZIP from this repo, exactly one SHA-256."""
        body = body or ""
        problem = None
        version = release_version(name, tag)
        hashes = {h.lower() for h in SHA256_RE.findall(body)}
        sha256 = next(iter(hashes)) if len(hashes) == 1 else None

        asset = select_zip(zips, version, sha256)
        if not zips:
            problem = "Release has no ZIP asset"
        elif asset is None:
            problem = (
                f"Release has {len(zips)} ZIP assets and none is selectable "
                "(versioned name or SHA-256 digest)"
            )
        elif not self.is_own_asset_url(asset.url):
            problem = "Asset URL does not belong to the configured repository"
        if sha256 is None and problem is None:
            problem = f"Release notes contain {len(hashes)} SHA-256 values, expected exactly 1"

        return Release(
            version=version,
            tag=tag,
            body=body,
            html_url=html_url,
            prerelease=prerelease,
            asset_name=asset.name if asset else None,
            asset_url=asset.url if asset else None,
            sha256=sha256,
            problem=problem,
        )

    async def async_download_asset(self, release: Release) -> bytes:
        """Download the release ZIP and verify its SHA-256.

        Redirects are followed by hand so that every hop is checked against
        `download_origins` and the token only goes to `auth_origins`.
        """
        if release.problem or not release.asset_url or not release.sha256:
            raise RepoError(release.problem or "Release is not installable")
        url = URL(release.asset_url)
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        try:
            async with asyncio.timeout(DOWNLOAD_TIMEOUT):
                for _ in range(MAX_REDIRECTS + 1):
                    if origin(url) not in self.download_origins:
                        raise RepoError(f"Download redirected to foreign host {url.host}")
                    async with self._session.get(
                        url,
                        headers=self._headers(self._download_accept(), url),
                        allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
                    ) as resp:
                        if resp.status in (301, 302, 303, 307, 308):
                            location = resp.headers.get("Location")
                            if not location:
                                raise RepoConnectionError("Redirect without Location")
                            url = url.join(URL(location))
                            continue
                        self._raise_for_status(resp, f"asset {release.asset_name}")
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            size += len(chunk)
                            if size > MAX_ASSET_BYTES:
                                raise RepoError("Asset exceeds size limit")
                            digest.update(chunk)
                            chunks.append(chunk)
                        break
                else:
                    raise RepoError("Too many redirects")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RepoConnectionError(self._scrub(f"{type(err).__name__}: {err}")) from err

        actual = digest.hexdigest()
        if actual != release.sha256:
            raise RepoError(
                f"SHA-256 mismatch: release notes say {release.sha256}, download is {actual}"
            )
        return b"".join(chunks)
