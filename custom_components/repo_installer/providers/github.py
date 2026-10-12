"""GitHub (github.com and GitHub Enterprise Server under /api/v3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp
from yarl import URL

from ..const import PROVIDER_GITHUB
from .base import (
    Origin,
    Provider,
    RateLimitError,
    Release,
    RepoNotFoundError,
    SchemaMismatchError,
    origin,
)

GITHUB_HOST = "github.com"
GITHUB_API = URL("https://api.github.com")

# github.com serves release assets via the API, which redirects to object
# storage. These are the only foreign hosts a download may be redirected to.
GITHUB_ASSET_HOSTS = (
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
)


class GitHubProvider(Provider):
    key = PROVIDER_GITHUB
    name = "GitHub"

    @property
    def _is_dotcom(self) -> bool:
        return (self.location.base_url.host or "").lower() == GITHUB_HOST

    @property
    def api_root(self) -> URL:
        if self._is_dotcom:
            return GITHUB_API
        return self.location.base_url / "api/v3"

    @property
    def repo_api_url(self) -> URL:
        owner, repo = self.location.path.split("/", 1)
        return self.api_root / "repos" / owner / repo

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _headers(self, accept: str, url: URL) -> dict[str, str]:
        return {**super()._headers(accept, url), "X-GitHub-Api-Version": "2022-11-28"}

    def _api_accept(self) -> str:
        return "application/vnd.github+json"

    def _download_accept(self) -> str:
        # Asset API URL + octet-stream = the file itself (via redirect)
        return "application/octet-stream"

    @property
    def download_origins(self) -> frozenset[Origin]:
        if self._is_dotcom:
            return frozenset(("https", host, 443) for host in GITHUB_ASSET_HOSTS)
        return frozenset({origin(self.location.base_url)})

    @property
    def auth_origins(self) -> frozenset[Origin]:
        if self._is_dotcom:
            return frozenset({origin(GITHUB_API)})
        return frozenset({origin(self.location.base_url)})

    def _raise_for_status(self, resp: aiohttp.ClientResponse, what: str) -> None:
        if resp.status in (403, 429) and (
            resp.headers.get("x-ratelimit-remaining") == "0" or resp.status == 429
        ):
            reset = resp.headers.get("x-ratelimit-reset", "")
            when = ""
            if reset.isdigit():
                when = " bis " + datetime.fromtimestamp(int(reset), timezone.utc).strftime(
                    "%H:%M UTC"
                )
            hint = "" if self._token else ", ohne Token nur 60 Anfragen/Stunde"
            raise RateLimitError(f"Rate-Limit erreicht{when}{hint}")
        super()._raise_for_status(resp, what)

    def _validate_repo(self, data: Any) -> None:
        if not (
            isinstance(data, dict)
            and "node_id" in data
            and isinstance(data.get("owner"), dict)
            and str(data.get("full_name", "")).lower() == self.location.path.lower()
        ):
            raise SchemaMismatchError("not a GitHub repository answer")

    async def async_get_latest_release(self, include_prereleases: bool) -> Release:
        api = self.repo_api_url
        if include_prereleases:
            releases = await self._get_json(api / "releases", {"per_page": "10"})
            releases = [r for r in releases or [] if not r.get("draft")]
            if not releases:
                raise RepoNotFoundError("no releases")
            data = releases[0]
        else:
            # /releases/latest skips drafts and pre-releases
            data = await self._get_json(api / "releases/latest")
        return self._build_release(
            tag=data.get("tag_name") or "",
            name=data.get("name"),
            body=data.get("body"),
            html_url=data.get("html_url"),
            prerelease=bool(data.get("prerelease")),
            # The API URL (not browser_download_url) works for private repos too
            zips=[
                (a.get("name", ""), a.get("url", ""))
                for a in data.get("assets") or []
                if a.get("name", "").lower().endswith(".zip")
            ],
        )

    def is_own_asset_url(self, url: str | URL) -> bool:
        url = URL(url)
        if origin(url) != origin(self.api_root):
            return False
        prefix = f"{self.repo_api_url.path}/releases/assets/"
        return url.path.lower().startswith(prefix.lower())
