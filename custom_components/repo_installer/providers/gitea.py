"""Forgejo and Gitea (same API under /api/v1)."""

from __future__ import annotations

from typing import Any

from yarl import URL

from ..const import PROVIDER_GITEA
from .base import Provider, Release, RepoNotFoundError, SchemaMismatchError, ZipAsset, origin


class GiteaProvider(Provider):
    key = PROVIDER_GITEA
    name = "Forgejo/Gitea"

    @property
    def repo_api_url(self) -> URL:
        owner, repo = self.location.path.split("/", 1)
        return self.location.base_url / "api/v1/repos" / owner / repo

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self._token}"}

    def _validate_repo(self, data: Any) -> None:
        if not (
            isinstance(data, dict)
            and isinstance(data.get("owner"), dict)
            and "login" in data["owner"]
            and str(data.get("full_name", "")).lower() == self.location.path.lower()
            and "clone_url" in data
            and "empty" in data  # Gitea/Forgejo only, GitHub has no such field
        ):
            raise SchemaMismatchError("not a Forgejo/Gitea repository answer")

    async def async_get_latest_release(self, include_prereleases: bool) -> Release:
        api = self.repo_api_url
        if include_prereleases:
            releases = await self._get_json(api / "releases", {"draft": "false", "limit": "10"})
            releases = [r for r in releases or [] if not r.get("draft")]
            if not releases:
                raise RepoNotFoundError("no releases")
            data = releases[0]
        else:
            # /releases/latest already skips drafts and pre-releases
            data = await self._get_json(api / "releases/latest")
            if data.get("draft") or data.get("prerelease"):
                raise RepoNotFoundError("latest release is a draft/pre-release")
        return self._build_release(
            tag=data.get("tag_name") or "",
            name=data.get("name"),
            body=data.get("body"),
            html_url=data.get("html_url"),
            prerelease=bool(data.get("prerelease")),
            zips=[
                ZipAsset(a.get("name", ""), a.get("browser_download_url", ""))
                for a in data.get("assets") or []
                if a.get("name", "").lower().endswith(".zip")
            ],
        )

    def is_own_asset_url(self, url: str | URL) -> bool:
        url = URL(url)
        base = self.location.base_url
        if origin(url) != origin(base):
            return False
        prefix = f"{base.path.rstrip('/')}/{self.location.path}/releases/download/"
        return url.path.lower().startswith(prefix.lower())
