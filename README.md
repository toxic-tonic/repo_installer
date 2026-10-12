# Repo Installer

[Deutsche Kurzfassung](README.de.md)

A Home Assistant custom integration that installs and updates other custom
integrations directly from **Git release ZIPs** – on GitHub, GitLab, Forgejo
or Gitea, including **self-hosted** instances. Everything happens in the
Home Assistant UI; no file uploads, no SSH.

It is meant as a **complement to HACS** for sources HACS does not cover:
your own Forgejo/Gitea/GitLab server, private forks, integrations that are
not published on GitHub. It does not replace HACS.

## Supported sources and auto-detection

| Provider | Hosts | Notes |
| --- | --- | --- |
| GitHub | github.com, GitHub Enterprise (`/api/v3`) | without token 60 API requests/hour |
| GitLab | gitlab.com, self-hosted (API v4) | nested groups; assets are release *links* |
| Forgejo / Gitea | any instance (API v1) | one shared adapter |

You enter the full repository URL, for example
`http://192.168.1.10:3000/me/my-integration` or `https://github.com/owner/repo`.
`github.com` and `gitlab.com` are recognised by their host. For anything
else the installer asks the candidate APIs (short timeouts, at most about
15 s) and picks the first one that answers correctly for exactly this
repository. The result ("Detected: Forgejo/Gitea") is shown and stored;
it is not detected again later. You can also choose the provider manually.
http and sub paths behind a reverse proxy (`https://host/git/owner/repo`)
work.

## Install and update

1. *Settings → Devices & services → Add integration → Repo Installer*
2. Enter the repository URL and the integration's **domain** (folder name
   under `custom_components`). Token (private repositories, GitHub rate
   limit), pre-releases and provider are optional.
3. The next step shows the detected provider and the latest release. If
   `custom_components/<domain>` does not exist yet, **Install now** installs
   it right away.
4. Restart Home Assistant when the repair notice "Restart required" appears.
   The installer never restarts Home Assistant itself.

Afterwards each entry has an update entity: new releases appear under
*Settings → Updates* (checked every 6 hours and on "Check for updates") and
are installed with one click. Old versions are kept as backup in
`custom_components/.repo_installer_backup/` (last two per integration).

**Change the token or provider:** entry → ⋮ → *Reconfigure*. If the API
rejects the token (HTTP 401/403), Home Assistant offers re-authentication
by itself.

> If the same integration is installed via HACS, remove it in HACS first.
> Otherwise HACS overwrites the version installed from your repository
> (for example your fork) on its next update.

## Release format expected from a repository

Any integration you want to install this way needs releases like this:

- a **tag** with the version (`v1.2.3`); the release **title** is the version
  (it may contain `+`, e.g. `2024.5.9+ultra1`)
- one **ZIP asset** (GitLab: a release link to a file in the same project).
  If there are several ZIPs, the one whose name contains the version is used
- `SHA-256: <64 hex characters>` of that ZIP in the **release description**
- ZIP content: exactly one folder `<domain>/` containing
  `<domain>/manifest.json`, whose `domain` and `version` match

## Security

- **SHA-256 is mandatory** for every provider; a release without it is not
  installable.
- **Host binding:** downloads may only come from the repository's host or
  the provider's known asset hosts (GitHub object storage). Redirects are
  followed hop by hop and checked; the token is never sent to object
  storage, and API redirects are not followed with a token at all.
- ZIP validation: one `<domain>/` folder only, manifest domain and version
  must match, no symlinks, no `..` paths, size limits.
- Downloaded content is **never executed**, only unpacked and moved into
  place by rename; on failure nothing is left behind.
- Tokens are stored only in the config entry and never logged.
- No external Python requirements.

## Limitations

- Only integrations (`custom_components/<domain>`), not themes, cards or
  other HACS categories.
- Only the latest release can be installed; no version picker, no
  automatic rollback (backups are kept, restore them manually).
- Self-hosted object storage redirects (S3/MinIO direct download) are
  rejected by the host binding.
- GitLab has no pre-release flag: a version with a pre-release part
  (`1.0.0-rc.1`) counts as pre-release.
- Renamed repositories: API redirects are not followed; reconfigure with
  the new URL.

## Installation via HACS (custom repository)

1. Open HACS → ⋮ (top right) → *Custom repositories*.
2. Repository: `https://github.com/toxic-tonic/repo_installer`,
   type: *Integration* → *Add*.
3. Search for "Repo Installer" in HACS, open it → *Download*.
4. Restart Home Assistant.
5. *Settings → Devices & services → Add integration → Repo Installer*.

## Manual installation

1. Download `repo_installer.zip` from the latest
   [release](https://github.com/toxic-tonic/repo_installer/releases/latest).
2. Unpack it into `/config/custom_components/` (result:
   `/config/custom_components/repo_installer/manifest.json`), replacing an
   existing `repo_installer` folder.
3. Restart Home Assistant and add the integration.

To let the installer update itself, add an entry for this repository with
the domain `repo_installer`.

## Scope and expectations

This is a community tool, maintained in spare time, **without any support
commitment**. It does what this README describes; there is no guarantee
of fixes, features or response times. Test updates before you rely on
them.

## Development

Development happens on a self-hosted Forgejo instance; this GitHub
repository is a **mirror**. Issues are welcome here. Pull requests are
welcome too, but they are applied manually on the self-hosted instance
and then mirrored back, so they are closed rather than merged on GitHub.

See [CHANGELOG.md](CHANGELOG.md) for changes and [SECURITY.md](SECURITY.md)
for reporting vulnerabilities.

## License

[MIT](LICENSE)
