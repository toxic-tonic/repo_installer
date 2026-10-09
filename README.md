# Forgejo Updater

Home-Assistant-Custom-Integration (`forgejo_updater`), die für selbst gehostete Custom Integrations Update-Entitäten aus Forgejo-Releases bereitstellt. Updates erscheinen unter **Einstellungen → Updates** und lassen sich dort installieren.

## Voraussetzungen an die Releases

- Release-Titel = Version, identisch zu `version` in `<domain>/manifest.json`
- genau ein `.zip`-Asset, das beim Entpacken direkt `<domain>/manifest.json` ergibt
- genau ein SHA-256 (64 Hex-Zeichen) des ZIPs in der Release-Beschreibung

## Einrichten

Einstellungen → Geräte & Dienste → Integration hinzufügen → „Forgejo Updater“:

| Feld | Beispiel |
| --- | --- |
| Forgejo-URL | `http://172.16.1.36:3000` |
| Repository | `toxic/linknlink-local` |
| Domain der Integration | `linknlink` |
| API-Token | leer (nur für private Repos) |
| Pre-Releases einbeziehen | aus |

Pro Integration ein Eintrag. Geprüft wird alle 6 Stunden und bei „Nach Updates suchen“.

## Installation eines Updates

1. ZIP-Asset herunterladen, SHA-256 gegen die Release-Beschreibung prüfen
2. ZIP-Inhalt prüfen (nur `<domain>/…`, Manifest-Domain und -Version passend, keine Symlinks/Pfad-Tricks)
3. alten Ordner nach `custom_components/.forgejo_updater_backup/<domain>-<alte-version>` verschieben (die letzten 2 bleiben), neuen Ordner per Rename einsetzen
4. Reparatur-Hinweis „Neustart erforderlich“; Home Assistant wird **nicht** automatisch neu gestartet

Zurückrollen: Ordner aus `.forgejo_updater_backup` zurück nach `custom_components/<domain>` kopieren, neu starten.
