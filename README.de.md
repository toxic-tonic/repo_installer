# Repo Installer (Kurzfassung)

[English README](README.md)

Home-Assistant-Custom-Integration, die andere Custom Integrations direkt aus **Git-Release-ZIPs** installiert und aktuell hält – von GitHub, GitLab, Forgejo und Gitea, auch **selbst gehostet** (http, Unterpfad). Ergänzt HACS für Quellen, die HACS nicht abdeckt, ersetzt es nicht.

## Einrichten

1. Einstellungen → Geräte & Dienste → Integration hinzufügen → „Repo Installer“
2. Vollständige Repo-URL (z. B. `http://172.16.1.36:3000/toxic/linknlink-local`) und Domain (Ordnername unter `custom_components`) eintragen. Token, Pre-Releases und Quellsystem sind optional; das Quellsystem wird automatisch erkannt.
3. „Erkannt: …“ prüfen. Fehlt die Integration noch: „Jetzt installieren“.
4. Nach dem Hinweis „Neustart erforderlich“ HA neu starten.

Updates erscheinen danach unter Einstellungen → Updates (Prüfung alle 6 h). Token oder Quellsystem ändern: Eintrag → ⋮ → „Neu konfigurieren“. Bei abgelehntem Token bietet HA die erneute Anmeldung selbst an.

> Ist dieselbe Integration über HACS installiert, sie vorher in HACS entfernen – sonst überschreibt HACS den Stand aus dem eigenen Repo (z. B. einen Fork).

## Erwartetes Release-Format

- Tag mit Version (`v1.2.3`), Release-Titel = Version
- ein ZIP-Asset (bei mehreren gilt das mit der Version im Namen; GitLab: Release-Link auf eine Datei im selben Projekt)
- `SHA-256: <hash>` des ZIPs in der Beschreibung
- ZIP-Inhalt: genau `<domain>/` mit `<domain>/manifest.json`, Domain und Version passend

## Sicherheit

SHA-256 ist Pflicht, Downloads nur vom Repo-Host bzw. bekannten Asset-Hosts (Host-Bindung), kein Token an Objektspeicher, keine API-Redirects mit Token, heruntergeladene Inhalte werden nie ausgeführt, Austausch per Umbenennen mit Backup der letzten 2 Stände.

Zurückrollen: Ordner aus `custom_components/.repo_installer_backup/` zurück nach `custom_components/<domain>` kopieren, HA neu starten.

## Installation des Installers

- **HACS:** HACS → ⋮ → Benutzerdefinierte Repositories → `https://github.com/<GITHUB_USER>/repo_installer`, Typ „Integration“ → herunterladen → HA neu starten.
- **Manuell:** `repo_installer.zip` aus dem neuesten Release nach `/config/custom_components/` entpacken, HA neu starten.

Community-Werkzeug ohne Supportversprechen. Entwicklung auf einer selbst gehosteten Forgejo-Instanz, GitHub ist ein Spiegel; Issues willkommen, Pull-Requests werden manuell übernommen. Details im [englischen README](README.md). Lizenz: [MIT](LICENSE).
