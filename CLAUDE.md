# CLAUDE.md – toxic/ha-forgejo-updater

Eigene Home-Assistant-Custom-Integration `forgejo_updater`: Update-Entitäten für Custom Integrations, die auf Forgejo released werden (Release-Schema wie `toxic/linknlink-local`). Forgejo: http://172.16.1.36:3000/toxic/ha-forgejo-updater

## Verbindliche Release-Regel

Gilt für jede Session, ohne Ausnahme:

1. **Jede Änderung unter `custom_components/forgejo_updater` endet mit einem Forgejo-Release.** Ohne Release gilt die Änderung als nicht ausgeliefert. Commits, die die Integration nicht berühren (z. B. diese Datei, Tests, README), lösen kein Release aus.
2. **Versionsschema:** `X.Y.Z` (eigenes Projekt, kein Upstream), fortlaufend ab dem letzten Release hochzählen.
   - Die Version steht identisch in `custom_components/forgejo_updater/manifest.json` (`version`) und im Release-Titel.
   - Git-Tag: `v<version>`, z. B. `v0.1.1`.
3. **Asset:** ZIP per `./deploy.sh zip`, Dateiname `forgejo_updater-<version>-<kurzhash>.zip`. Nach dem Entpacken in `/config/custom_components/` entsteht direkt `forgejo_updater/manifest.json`. Genau ein ZIP-Asset pro Release.
4. **Release-Beschreibung** (deutsch, kurz):
   - Änderungen gegenüber dem vorherigen Release
   - Commit-Hash
   - SHA-256 des ZIPs (genau ein 64-stelliger Hex-Wert in der Beschreibung – die Integration liest ihn von dort)
   - Testergebnis
   - Feste Einspielanleitung: ZIP herunterladen, in Studio Code Server nach `/config/custom_components/` hochladen und entpacken (vorhandenen Ordner `forgejo_updater` vorher ersetzen), HA neu starten. Ab installierter 0.1.0 alternativ: Einstellungen → Updates.
5. **Vor dem Release müssen die HA-Tests grün sein.** Bei roten Tests gibt es kein Release, stattdessen an Tobias melden.
6. **Releases werden nie gelöscht oder überschrieben.** Ein fehlerhaftes Release wird durch ein neues mit höherer Version ersetzt.
7. **Rückmeldung an Tobias nach jedem Release:** nur Version, Kurzliste der Änderungen und die direkte Download-URL des Assets.
8. **`dist/` enthält lokal nur das ZIP des aktuellen Releases** (`dist/` ist in `.gitignore`).

## Arbeitsumgebung (Host `dev`)

- Repo-Arbeitskopie: `/home/dev/ha-forgejo-updater`. `deploy.sh` und `dist/` liegen im Repo-Root; `deploy.sh zip` verlangt einen sauberen `master`, der `origin/master` entspricht, und baut aus `git archive HEAD`.
- HA-Tests (HA 2026.2.3, venv aus linknlink-local):
  `cd /home/dev/ha-forgejo-updater && /home/dev/linknlink-local/.venv-ha/bin/pytest -q -p no:cacheprovider`
  - `tests/test_live.py` (Marker `live`) liest nur (GET) von `toxic/linknlink-local` und muss das aktuelle linknlink-Release als latest erkennen. Bei einem neuen linknlink-Release `EXPECTED`/`EXPECTED_SHA` dort nachziehen.
- Forgejo-API: `http://172.16.1.36:3000/api/v1/repos/toxic/ha-forgejo-updater`. Token über `git credential fill` (host `172.16.1.36:3000`), nie ausgeben. Das Token darf keine Repos anlegen.
  - Release anlegen: `POST /releases` mit `tag_name`, `name`, `body`
  - Asset hochladen: `POST /releases/{id}/assets?name=<datei>` (multipart, Feld `attachment`)
- Direkte Asset-URL: `http://172.16.1.36:3000/toxic/ha-forgejo-updater/releases/download/<tag>/<datei>` (`+` als `%2B`)

## Design-Grenzen (nicht aufweichen)

- Keine externen Requirements, nur was HA mitbringt (aiohttp, yarl, voluptuous).
- HA-Start wartet nie auf Netzwerk: erster Abruf als Background-Task, Forgejo offline → Entität `unavailable`.
- Installation nur: Asset aus dem konfigurierten Repo, SHA-256 aus der Release-Beschreibung passt, ZIP enthält nur `<domain>/…` mit passender Manifest-Version, keine Symlinks/`..`. Heruntergeladenes wird nie ausgeführt, nur entpackt und per Rename getauscht.
- Backups unter `/config/custom_components/.forgejo_updater_backup/<domain>-<alte-version>`, die letzten 2 pro Domain bleiben.
- Nach Installation nur Reparatur-Hinweis „Neustart erforderlich“, nie selbst neu starten.
