# CLAUDE.md – toxic/repo_installer

Eigene Home-Assistant-Custom-Integration `repo_installer` („Repo Installer“): installiert Custom Integrations aus Release-ZIPs von GitHub, GitLab, Forgejo und Gitea und hält sie über Update-Entitäten aktuell. Forgejo: http://172.16.1.36:3000/toxic/repo_installer

## Verbindliche Release-Regel

Gilt für jede Session, ohne Ausnahme:

1. **Jede Änderung unter `custom_components/repo_installer` endet mit einem Forgejo-Release.** Ohne Release gilt die Änderung als nicht ausgeliefert. Commits, die die Integration nicht berühren (z. B. diese Datei, Tests, README), lösen kein Release aus.
2. **Versionsschema:** `X.Y.Z` (eigenes Projekt, kein Upstream), fortlaufend ab dem letzten Release hochzählen. Startversion `0.1.0`.
   - Die Version steht identisch in `custom_components/repo_installer/manifest.json` (`version`) und im Release-Titel.
   - Git-Tag: `v<version>`, z. B. `v0.1.1`.
3. **Asset:** ZIP per `./deploy.sh zip`, Dateiname `repo_installer-<version>-<kurzhash>.zip`. Nach dem Entpacken in `/config/custom_components/` entsteht direkt `repo_installer/manifest.json`. Genau ein ZIP-Asset pro Release.
4. **Release-Beschreibung** (deutsch, kurz):
   - Änderungen gegenüber dem vorherigen Release
   - Commit-Hash
   - `SHA-256: <hash>` des ZIPs (genau ein 64-stelliger Hex-Wert in der Beschreibung – die Integration liest ihn von dort)
   - Testergebnis
   - Feste Einspielanleitung: ZIP herunterladen, in Studio Code Server nach `/config/custom_components/` hochladen und entpacken (vorhandenen Ordner `repo_installer` vorher ersetzen), HA neu starten. Ab installierter 0.1.0 alternativ: Einstellungen → Updates (Eintrag für `toxic/repo_installer` mit Domain `repo_installer`).
5. **Vor dem Release müssen die HA-Tests grün sein.** Bei roten Tests gibt es kein Release, stattdessen an Tobias melden.
6. **Releases werden nie gelöscht oder überschrieben.** Ein fehlerhaftes Release wird durch ein neues mit höherer Version ersetzt.
7. **Rückmeldung an Tobias nach jedem Release:** nur Version, Kurzliste der Änderungen und die direkte Download-URL des Assets.
8. **`dist/` enthält lokal nur das ZIP des aktuellen Releases** (`dist/` ist in `.gitignore`).

## Release-Format, das der Installer von Fremd-Repos erwartet

Vorlage für jede eigene Integration, die über den Repo Installer verteilt wird (Forgejo, Gitea, GitHub oder GitLab):

- **Tag** mit der Version, z. B. `v1.2.3`. **Release-Titel** = Version (darf `+` enthalten, z. B. `2024.5.9+ultra1`; Tags können das oft nicht). Der Titel hat Vorrang, wenn er mit einer Ziffer (oder `v` + Ziffer) beginnt, sonst gilt der Tag ohne führendes `v`.
- **Genau ein `.zip`-Asset** im Release:
  - Forgejo/Gitea/GitHub: hochgeladene Datei.
  - GitLab: Release-Link (`assets.links`) auf eine Datei in *diesem* Projekt (Generic Package Registry `…/api/v4/projects/<id|pfad>/packages/generic/…` oder Projekt-Upload). Externe Links werden abgelehnt.
- **Beschreibung** enthält genau einen SHA-256 des ZIPs, Konvention: `SHA-256: <64 Hex-Zeichen>`.
- **ZIP-Inhalt:** genau ein Ordner `<domain>/` mit `<domain>/manifest.json`; `domain` und `version` im Manifest passen zur Ziel-Domain bzw. zur Release-Version. Keine Symlinks, keine `..`-Pfade, max. 50 MB gepackt / 200 MB entpackt.
- **Pre-Releases:** Forgejo/Gitea/GitHub über das Pre-Release-Flag. GitLab kennt kein Flag: dort gilt ein Release als Pre-Release, wenn die Version einen Pre-Release-Teil hat (`1.0.0-rc.1`, `1.0.0b1`).

## Arbeitsumgebung (Host `dev`)

- Repo-Arbeitskopie: `/home/dev/repo_installer`. `deploy.sh` und `dist/` liegen im Repo-Root; `deploy.sh zip` verlangt einen sauberen `master`, der `origin/master` entspricht, und baut aus `git archive HEAD`.
- Vorgänger `forgejo_updater` liegt unverändert in `/home/dev/ha-forgejo-updater`, Branch `pre-rename` (ffe70e7) als Sicherung, in beiden Arbeitskopien.
- HA-Tests (HA 2026.2.3, venv aus linknlink-local):
  - Unit: `cd /home/dev/repo_installer && /home/dev/linknlink-local/.venv-ha/bin/pytest -q -p no:cacheprovider` (Live-Tests werden übersprungen)
  - Live: dieselbe Zeile mit `--live -m live`. Alle Live-Tests (Marker `live`) lesen nur und installieren nur in Temp-Verzeichnisse.
  - Vor einem Release laufen beide; das Testergebnis in der Release-Beschreibung nennt Unit und Live getrennt.
  - `tests/test_live.py`: `toxic/linknlink-local` muss als Forgejo/Gitea erkannt werden, das aktuelle linknlink-Release ist latest. Bei einem neuen linknlink-Release `EXPECTED`/`EXPECTED_SHA` dort nachziehen.
  - `tests/test_live_external.py`: `hacs/integration` (GitHub) und `gitlab-org/cli` (gitlab.com): Erkennung, latest, Asset-URL, Download über die erlaubten Hosts (gegen Dummy-SHA, muss mit „mismatch“ scheitern), Ablehnung ohne SHA-256 ohne Reste. GitHub ohne Token: 60 Anfragen/Stunde.
- Forgejo-API: `http://172.16.1.36:3000/api/v1/repos/toxic/repo_installer`. Token über `git credential fill` (host `172.16.1.36:3000`), nie ausgeben. Das Token darf keine Repos anlegen.
  - Release anlegen: `POST /releases` mit `tag_name`, `name`, `body`
  - Asset hochladen: `POST /releases/{id}/assets?name=<datei>` (multipart, Feld `attachment`)
- Direkte Asset-URL: `http://172.16.1.36:3000/toxic/repo_installer/releases/download/<tag>/<datei>` (`+` als `%2B`)

## Aufbau

- `providers/`: ein Adapter je Quellsystem (`gitea.py` für Forgejo+Gitea, `github.py`, `gitlab.py`) auf gemeinsamer Basis `base.py` (Release-Modell, Download mit SHA-256 und Host-Bindung); `__init__.py` enthält URL-Parsing und Autoerkennung.
- `config_flow.py`: URL + Domain → Erkennung → Bestätigung „Erkannt: …“ mit „Jetzt installieren“, wenn der Zielordner fehlt. Neu konfigurieren (Token, Quellsystem) und Reauth bei HTTP 401/403.
- `update.py` / `coordinator.py`: Update-Entität je Eintrag, Prüfung alle 6 h. Nicht installiert: installierte Version leer (`""`, nicht `None` – sonst Zustand `unknown`, und das Frontend blendet Installieren und den Eintrag unter Updates aus), übersetzter Hinweis über `release_summary` und Release-Notes.
- `installer.py`: ZIP prüfen, entpacken, per Rename tauschen (läuft im Executor). `version.py`: Versionsvergleich.

## Design-Grenzen (nicht aufweichen)

- Keine externen Requirements, nur was HA mitbringt (aiohttp, yarl, voluptuous).
- HA-Start wartet nie auf Netzwerk: erster Abruf als Background-Task, Anbieter offline → Entität `unavailable`. GitHub-Rate-Limit mit bekanntem Stand → letzter Stand bleibt, nur Warnung im Log.
- Quellsystem wird nur im Config Flow erkannt (max. ca. 15 s) und im Eintrag gespeichert, nie bei späteren Abfragen.
- Installation nur: Asset aus dem konfigurierten Repo, SHA-256 aus der Release-Beschreibung passt (Pflicht für alle Anbieter), ZIP enthält nur `<domain>/…` mit passender Manifest-Domain und -Version, keine Symlinks/`..`, Größenlimit. Heruntergeladenes wird nie ausgeführt, nur entpackt und per Rename getauscht.
- Host-Bindung: Redirects werden von Hand verfolgt, jeder Hop muss in der Host-Liste des Adapters stehen (Repo-Host; github.com zusätzlich die GitHub-Objektspeicher-Hosts, live bestätigt: `release-assets.githubusercontent.com`; gitlab.com liefert Release-Links und Generic Packages selbst aus, live bestätigt, kein Fremd-Host). Token geht nur an den API-/Repo-Host, nie an Objektspeicher. API-Redirects werden nicht verfolgt.
- Tokens nur im Config-Entry, nie in Logs oder Fehlermeldungen.
- Fehlender Zielordner: wird angelegt, kein Backup. Vorhandener Ordner: Backup unter `/config/custom_components/.repo_installer_backup/<domain>-<alte-version>`, die letzten 2 pro Domain bleiben. Bei Fehlschlag keine Reste.
- Nach Installation nur Reparatur-Hinweis „Neustart erforderlich“ (verschwindet nach dem Neustart), nie selbst neu starten.
