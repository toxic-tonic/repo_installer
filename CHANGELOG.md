# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow
`X.Y.Z` (tag `v<version>`). Each section is used verbatim as the release
notes of that version; the release adds the `SHA-256:` line.

## [0.2.0] - unreleased

### Added
- Store preparation: `hacs.json` (HACS installs the tagged source,
  minimum Home Assistant 2026.2.0), English README (German short version
  in `README.de.md`), issue templates, MIT license.
- Brand icon in `custom_components/repo_installer/brand/` (shown by Home
  Assistant 2026.3 and later, used by HACS).
- `SECURITY.md`: vulnerabilities are reported via GitHub's private
  vulnerability reporting.
- Every release ships two identical ZIP assets: `repo_installer.zip`
  (fixed name for HACS) and `repo_installer-<version>-<hash>.zip`.
- Deterministic ZIP build (`scripts/build_zip.py`): same commit, same
  SHA-256 on Forgejo and GitHub.
- GitHub workflows: validation (HACS, hassfest, unit tests against the
  minimum and the current Home Assistant) and releases built from this
  changelog, started by a tag or manually for an existing tag.

### Changed
- Releases with several ZIP assets: the asset whose name contains the
  version is used; otherwise the one whose provider digest (GitHub)
  matches the SHA-256 in the release notes. Ambiguous releases are
  rejected as before.
- `manifest.json`: GitHub documentation and issue tracker, codeowners.
- Example URLs in the setup dialog moved into placeholders (hassfest).

### Fixed
- Live tests work with the current Home Assistant test plugin, which
  also blocks DNS resolution.

## [0.1.1] - 2026-10-12

### Added
- Reconfigure: change or remove the token and switch the Git provider;
  new settings are checked against the API before they are saved.
- Re-authentication: HTTP 401/403 from the API makes Home Assistant offer
  a new login by itself. The GitHub rate limit stays a separate message.
- Read-only live smoke tests for GitHub and gitlab.com, skipped by default.

### Changed
- Not installed: the installed version is left empty; a translated hint
  (English, German) is shown in the summary and the release notes. Install
  stays available in the UI.

### Fixed
- gitlab.com download hosts limited to gitlab.com (checked live); the
  former `storage.googleapis.com` entry was not needed.

## [0.1.0] - 2026-10-12

### Added
- First release: installs and updates custom integrations from release
  ZIPs on GitHub, GitLab, Forgejo and Gitea, including self-hosted
  instances with http and sub paths.
- Config flow with automatic provider detection and "install now" when
  the integration is not installed yet.
- Update entity per entry, checked every 6 hours; mandatory SHA-256 from
  the release notes, host binding for downloads, backup of the last two
  versions, "restart required" repair issue.
