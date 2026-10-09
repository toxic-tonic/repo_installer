"""Minimal async Forgejo client (read-only)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib

import aiohttp
from yarl import URL

from .const import API_TIMEOUT, DOWNLOAD_TIMEOUT, MAX_ASSET_BYTES, SHA256_RE


class ForgejoError(Exception):
    """Base error."""


class ForgejoConnectionError(ForgejoError):
    """Forgejo not reachable or answered with garbage."""


class ForgejoAuthError(ForgejoError):
    """Token rejected."""


class ForgejoNotFoundError(ForgejoError):
    """Repository or release not found."""


@dataclass(frozen=True)
class Release:
    """The parts of a Forgejo release we care about."""

    version: str
    tag: str
    body: str
    html_url: str | None
    prerelease: bool
    asset_name: str | None = None
    asset_url: str | None = None
    sha256: str | None = None
    problem: str | None = None  # set when the release cannot be installed


class ForgejoClient:
    """Talks to one repository on one Forgejo instance."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        repository: str,
        token: str | None = None,
    ) -> None:
        self._session = session
        self.base_url = URL(base_url.rstrip("/"))
        self.owner, self.repo = repository.split("/", 1)
        self._headers = {"Accept": "application/json"}
        if token:
            self._headers["Authorization"] = f"token {token}"

    @property
    def _api(self) -> URL:
        return self.base_url / "api/v1/repos" / self.owner / self.repo

    async def _get_json(self, url: URL, params: dict[str, str] | None = None):
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if resp.status in (401, 403):
                    raise ForgejoAuthError(f"HTTP {resp.status} for {url}")
                if resp.status == 404:
                    raise ForgejoNotFoundError(f"HTTP 404 for {url}")
                if resp.status != 200:
                    raise ForgejoConnectionError(f"HTTP {resp.status} for {url}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ForgejoConnectionError(f"{type(err).__name__}: {err}") from err

    async def async_get_repo(self) -> dict:
        """Return repository metadata (used to validate the config)."""
        return await self._get_json(self._api)

    async def async_get_latest_release(self, include_prereleases: bool) -> Release:
        """Return the newest published release."""
        if include_prereleases:
            releases = await self._get_json(
                self._api / "releases", {"draft": "false", "limit": "10"}
            )
            releases = [r for r in releases if not r.get("draft")]
            if not releases:
                raise ForgejoNotFoundError("no releases")
            data = releases[0]
        else:
            # /releases/latest already skips drafts and pre-releases
            data = await self._get_json(self._api / "releases/latest")
            if data.get("draft") or data.get("prerelease"):
                raise ForgejoNotFoundError("latest release is a draft/pre-release")
        return self._parse_release(data)

    def _parse_release(self, data: dict) -> Release:
        tag = data.get("tag_name") or ""
        version = (data.get("name") or "").strip() or tag.removeprefix("v")
        body = data.get("body") or ""
        problem = None

        zips = [a for a in data.get("assets") or [] if a.get("name", "").endswith(".zip")]
        asset = zips[0] if len(zips) == 1 else None
        if asset is None:
            problem = f"Release has {len(zips)} ZIP assets, expected exactly 1"
        elif not self.is_own_asset_url(asset.get("browser_download_url", "")):
            problem = "Asset URL does not belong to the configured repository"

        hashes = {h.lower() for h in SHA256_RE.findall(body)}
        sha256 = hashes.pop() if len(hashes) == 1 else None
        if sha256 is None and problem is None:
            problem = f"Release notes contain {len(hashes)} SHA-256 values, expected exactly 1"

        return Release(
            version=version,
            tag=tag,
            body=body,
            html_url=data.get("html_url"),
            prerelease=bool(data.get("prerelease")),
            asset_name=asset.get("name") if asset else None,
            asset_url=asset.get("browser_download_url") if asset else None,
            sha256=sha256,
            problem=problem,
        )

    def is_own_asset_url(self, url: str | URL) -> bool:
        """Only accept downloads from this repository on this Forgejo."""
        url = URL(url)
        base = self.base_url
        if (url.scheme, url.host, url.port) != (base.scheme, base.host, base.port):
            return False
        prefix = f"{base.path.rstrip('/')}/{self.owner}/{self.repo}/releases/download/"
        return url.path.lower().startswith(prefix.lower())

    async def async_download_asset(self, release: Release) -> bytes:
        """Download the release ZIP and verify its SHA-256."""
        if release.problem or not release.asset_url or not release.sha256:
            raise ForgejoError(release.problem or "Release is not installable")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        try:
            async with asyncio.timeout(DOWNLOAD_TIMEOUT):
                async with self._session.get(
                    release.asset_url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
                ) as resp:
                    # Forgejo may redirect to /attachments/…, but never off-host
                    if (resp.url.scheme, resp.url.host, resp.url.port) != (
                        self.base_url.scheme,
                        self.base_url.host,
                        self.base_url.port,
                    ):
                        raise ForgejoError(f"Download redirected to {resp.url.host}")
                    if resp.status != 200:
                        raise ForgejoConnectionError(f"HTTP {resp.status} for asset")
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > MAX_ASSET_BYTES:
                            raise ForgejoError("Asset exceeds size limit")
                        digest.update(chunk)
                        chunks.append(chunk)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ForgejoConnectionError(f"{type(err).__name__}: {err}") from err

        actual = digest.hexdigest()
        if actual != release.sha256:
            raise ForgejoError(
                f"SHA-256 mismatch: release notes say {release.sha256}, download is {actual}"
            )
        return b"".join(chunks)
