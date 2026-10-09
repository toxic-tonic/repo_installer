"""Constants for Forgejo Updater."""

from datetime import timedelta
import re

DOMAIN = "forgejo_updater"

CONF_URL = "url"
CONF_REPOSITORY = "repository"
CONF_TARGET_DOMAIN = "target_domain"
CONF_TOKEN = "token"
CONF_INCLUDE_PRERELEASES = "include_prereleases"

UPDATE_INTERVAL = timedelta(hours=6)

API_TIMEOUT = 20  # seconds, per API request
DOWNLOAD_TIMEOUT = 120  # seconds, whole asset download
MAX_ASSET_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
KEEP_BACKUPS = 2

BACKUP_DIR = ".forgejo_updater_backup"
STAGING_DIR = ".forgejo_updater_staging"

DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA256_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
