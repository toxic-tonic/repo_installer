# Security policy

## Supported versions

Only the latest release receives fixes. Please update before reporting.

| Version | Supported |
| ------- | --------- |
| latest `0.x` release | yes |
| older releases | no |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
**private vulnerability reporting** instead: on
`https://github.com/toxic-tonic/repo_installer` open the **Security** tab
and click **Report a vulnerability**. Only the maintainer can see the report.

Include the installer version, the Home Assistant version, the Git
provider involved and steps to reproduce. You will get an answer as time
permits; this is a community project without a support commitment (see
the README, "Scope and expectations").

Areas that matter most: SHA-256 verification, host binding of downloads,
ZIP validation (paths, symlinks, size) and token handling.
