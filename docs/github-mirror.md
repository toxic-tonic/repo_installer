# GitHub-Spiegel einrichten (Forgejo → GitHub)

Kurz und handytauglich. Platzhalter `<GITHUB_USER>` vorher ersetzen (`scripts/placeholders.py apply GITHUB_USER=<name>`).

## 1. GitHub-Repo anlegen

1. github.com → **+** → *New repository*
2. Owner `<GITHUB_USER>`, Name **`repo_installer`**, **Public**
3. **Leer** lassen: kein README, keine Lizenz, kein .gitignore
4. *Create repository*
5. Repo → ⚙ *Settings* → *General*:
   - **Description:** `Install and update Home Assistant custom integrations from GitHub, GitLab, Forgejo and Gitea releases – a self-hosted complement to HACS.`
   - **Topics** (Zahnrad neben „About“): `home-assistant`, `hacs`, `hacs-integration`, `custom-integration`, `forgejo`, `gitea`, `gitlab`, `self-hosted`
   - *Features* → **Issues** aktiviert lassen
6. *Settings* → *Actions* → *General* → *Workflow permissions*: **Read repository contents** (Standard). Der Release-Job holt sich `contents: write` selbst.
7. *Settings* → *Advanced Security* (bzw. *Code security*) → **Private vulnerability reporting: Enable**. `SECURITY.md` verweist nur darauf („Security“-Tab → „Report a vulnerability“), es gibt keine Mailadresse.

## 2. Token für den Spiegel

1. GitHub → Profilbild → *Settings* → *Developer settings* → *Personal access tokens* → **Fine-grained tokens** → *Generate new token*
2. Name `forgejo-mirror-repo_installer`, **Expiration** setzen (z. B. 1 Jahr, Termin notieren)
3. *Repository access* → **Only select repositories** → `<GITHUB_USER>/repo_installer`
4. *Permissions* → *Repository permissions*, genau diese zwei (Metadata: read setzt GitHub automatisch), sonst nichts:
   - **Contents: Read and write**
   - **Workflows: Read and write** – Pflicht: ohne dieses Recht lehnt GitHub jeden Push ab, der Dateien unter `.github/workflows/` enthält
5. Erzeugen, Token einmalig kopieren

## 3. Push-Mirror in Forgejo

1. Forgejo → `toxic/repo_installer` → *Einstellungen* → *Repository* → Abschnitt **Spiegeleinstellungen**
2. *Push-Mirror hinzufügen*:
   - Git-Remote-URL: `https://github.com/<GITHUB_USER>/repo_installer.git`
   - Benutzername: `<GITHUB_USER>`, Passwort: **das Token**
   - **Bei Push synchronisieren** ✓
   - Intervall: `8h` (Rückfall, falls ein Push-Sync ausfällt)
3. Speichern → **Jetzt synchronisieren**
4. Auf GitHub prüfen: Commits da, unter *Tags* auch alle `v*`-Tags. Der Forgejo-Push-Mirror spiegelt alle Refs (Branches und Tags).
5. **Erster Sync:** Er pusht mehrere Tags auf einmal; bei mehr als drei Tags in einem Push erzeugt GitHub **keine** Tag-Ereignisse, der Release-Workflow startet also nicht von selbst. Dann: GitHub → *Actions* → *Release* → *Run workflow* → Feld `tag` = z. B. `v0.2.0` → *Run*. Dieselben Prüfungen wie beim Tag-Push (Validierung, Tag/Manifest/CHANGELOG, nie überschreiben).
6. `v0.1.0` und `v0.1.1` werden auf GitHub **nicht** nachgebaut: Ihr Commit enthält noch keinen Release-Workflow, der Workflow lehnt sie ab. Sie bleiben reine Tags; das erste GitHub-Release ist 0.2.0.

## Regeln

- **Auf GitHub nie direkt committen**, nie über die GitHub-Oberfläche Dateien ändern, keine Releases von Hand. Der nächste Spiegel-Push würde abweichende Stände überschreiben bzw. scheitern.
- Pull-Requests auf GitHub: Änderung lokal nach Forgejo übernehmen (Patch: `https://github.com/<GITHUB_USER>/repo_installer/pull/<nr>.patch`, `git am`), dort normal committen und releasen; PR auf GitHub mit Dank und Verweis auf den Commit schließen.
- Die Workflows committen und pushen nie.

## Release-Ablauf ab dann

1. Forgejo-Release nach Standing Rule (`./deploy.sh zip`, beide ZIPs hochladen)
2. Der Mirror überträgt Commit und Tag nach GitHub
3. Der GitHub-Workflow *Release* validiert (HACS, hassfest), prüft Tag gegen `manifest.json` und `CHANGELOG.md` und baut mit `scripts/build_zip.py` dasselbe ZIP
4. **Kontrolle:** SHA-256 in der GitHub-Release-Beschreibung muss exakt der SHA-256 im Forgejo-Release entsprechen. Der Bau ist deterministisch (gleicher Commit → gleiche Bytes); eine Abweichung ist ein Fehler – Release nicht verwenden, Ursache klären.

## Fehlerfälle

| Woran erkennbar | Nachziehen |
| --- | --- |
| Tag fehlt auf GitHub, Forgejo-Spiegeleinstellungen zeigen Fehler/alte „Letzte Aktualisierung“ | Token abgelaufen? Neues Token eintragen → *Jetzt synchronisieren* |
| Tag da, aber kein *Release*-Lauf unter *Actions* (z. B. mehr als drei Tags auf einmal gepusht) | *Actions* → *Release* → *Run workflow* mit dem Tag |
| Tag da, aber kein Release; GitHub → *Actions* → *Release* rot | Log lesen. Validierung rot: Fehler auf Forgejo beheben, **neue Version** releasen (Tags werden nie verschoben). Vorübergehender Fehler (Runner, Netz): *Re-run all jobs* |
| Workflow bricht mit „already exists“ ab | Release existiert schon, wird absichtlich nie überschrieben – nichts tun |
| SHA-256 GitHub ≠ Forgejo | GitHub-Release als *Pre-release* markieren (nicht löschen, Releases werden nie gelöscht), Ursache klären, Korrektur als neue Version |
