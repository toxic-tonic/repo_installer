# Repo Installer

Home-Assistant-Custom-Integration (`repo_installer`), die Custom Integrations direkt aus Git-Releases installiert und aktuell hält – komplett über die HA-Oberfläche, ohne Dateien hochzuladen. Unterstützt GitHub, GitLab, Forgejo und Gitea (auch selbst gehostet, mit http und Unterpfad). Updates erscheinen unter **Einstellungen → Updates**.

## Einrichten

Einstellungen → Geräte & Dienste → Integration hinzufügen → „Repo Installer“:

| Feld | Beispiel |
| --- | --- |
| Repository-URL | `http://172.16.1.36:3000/toxic/linknlink-local` oder `https://github.com/owner/repo` |
| Domain der Integration | `linknlink` |
| API-Token | leer (nur für private Repos; bei GitHub gegen das Rate-Limit) |
| Pre-Releases einbeziehen | aus |
| Quellsystem | Automatisch |

> **HACS:** Ist dieselbe Integration bereits über HACS installiert, sie vorher in HACS entfernen. Sonst überschreibt HACS beim nächsten Update den Stand aus dem eigenen Repo (z. B. einen Fork).

Der nächste Schritt zeigt das erkannte Quellsystem („Erkannt: Forgejo/Gitea“) und das neueste Release. Existiert `custom_components/<domain>` noch nicht, steht dort **„Jetzt installieren“**. Pro Integration ein Eintrag. Geprüft wird alle 6 Stunden und bei „Nach Updates suchen“.

Token oder Quellsystem später ändern: Eintrag → ⋮ → **Neu konfigurieren**. Lehnt die API das Token ab (HTTP 401/403), bietet HA die erneute Anmeldung von selbst an. Das GitHub-Rate-Limit löst keine erneute Anmeldung aus; mit bekanntem Stand bleibt die Entität verfügbar, nur eine Warnung im Log.

## Voraussetzungen an die Releases

- Tag mit der Version, Release-Titel = Version, identisch zu `version` in `<domain>/manifest.json`
- genau ein `.zip`-Asset (GitLab: Release-Link auf eine Datei im selben Projekt), das beim Entpacken direkt `<domain>/manifest.json` ergibt
- genau ein SHA-256 des ZIPs in der Release-Beschreibung (`SHA-256: <hash>`)

## Installation

1. ZIP-Asset herunterladen (Redirects nur auf den Repo-Host bzw. bekannte Asset-Hosts), SHA-256 gegen die Release-Beschreibung prüfen
2. ZIP-Inhalt prüfen (nur `<domain>/…`, Manifest-Domain und -Version passend, keine Symlinks/Pfad-Tricks, Größenlimit)
3. vorhandenen Ordner nach `custom_components/.repo_installer_backup/<domain>-<alte-version>` verschieben (die letzten 2 bleiben), neuen Ordner per Rename einsetzen; bei Erstinstallation ohne Backup
4. Reparatur-Hinweis „Neustart erforderlich“; Home Assistant wird **nicht** automatisch neu gestartet

Zurückrollen: Ordner aus `.repo_installer_backup` zurück nach `custom_components/<domain>` kopieren, neu starten.
