"""Constants for Repo Installer."""

from datetime import timedelta
import re

DOMAIN = "repo_installer"

CONF_URL = "url"  # full repository URL as entered (normalized)
CONF_BASE_URL = "base_url"  # web root of the Git instance, incl. sub path
CONF_REPO_PATH = "repo_path"  # owner/repo, for GitLab also group/sub/project
CONF_PROVIDER = "provider"
CONF_TARGET_DOMAIN = "target_domain"
CONF_TOKEN = "token"
CONF_INCLUDE_PRERELEASES = "include_prereleases"
CONF_INSTALL_NOW = "install_now"

PROVIDER_AUTO = "auto"
PROVIDER_GITHUB = "github"
PROVIDER_GITLAB = "gitlab"
PROVIDER_GITEA = "gitea"  # Forgejo and Gitea share one adapter

UPDATE_INTERVAL = timedelta(hours=6)

API_TIMEOUT = 20  # seconds, per API request
DETECT_REQUEST_TIMEOUT = 5  # seconds, per probe during auto-detection
DETECT_TOTAL_TIMEOUT = 15  # seconds, whole auto-detection
DOWNLOAD_TIMEOUT = 120  # seconds, whole asset download incl. redirects
MAX_REDIRECTS = 5
MAX_ASSET_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
KEEP_BACKUPS = 2

BACKUP_DIR = ".repo_installer_backup"
STAGING_DIR = ".repo_installer_staging"

# Installed version when custom_components/<domain> does not exist: empty
# keeps the update entity "on" (first install offered); the translated hint
# comes from entity.update.<TRANSLATION_KEY> in strings.json.
NOT_INSTALLED = ""
TRANSLATION_KEY = "integration"

DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")
SHA256_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
