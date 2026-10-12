# GitHub-Spiegel einrichten (Forgejo → GitHub)

Kurz und handytauglich. Platzhalter `<GITHUB_USER>` vorher ersetzen (`scripts/placeholders.py`).

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

## 2. Token für den Spiegel

1. GitHub → Profilbild → *Settings* → *Developer settings* → *Personal access tokens* → **Fine-grained tokens** → *Generate new token*
2. Name `forgejo-mirror-repo_installer`, **Expiration** setzen (z. B. 1 Jahr, Termin notieren)
3. *Repository access* → **Only select repositories** → `<GITHUB_USER>/repo_installer`
4. *Permissions* → *Repository permissions* → **Contents: Read and write** (Metadata: read wird automatisch gesetzt), sonst nichts
5. Erzeugen, Token einmalig kopieren

> Der Push-Mirror pusht auch die Workflow-Dateien unter `.github/workflows/`. Lehnt GitHub den Push mit „refusing to allow … to create or update workflow … without `workflows` permission“ ab, im Token zusätzlich **Workflows: Read and write** setzen. (Unsicher, wie GitHub das bei fine-grained Tokens aktuell handhabt – beim ersten Sync prüfen.)

## 3. Push-Mirror in Forgejo

1. Forgejo → `toxic/repo_installer` → *Einstellungen* → *Repository* → Abschnitt **Spiegeleinstellungen**
2. *Push-Mirror hinzufügen*:
   - Git-Remote-URL: `https://github.com/<GITHUB_USER>/repo_installer.git`
   - Benutzername: `<GITHUB_USER>`, Passwort: **das Token**
   - **Bei Push synchronisieren** ✓
   - Intervall: `8h` (Rückfall, falls ein Push-Sync ausfällt)
3. Speichern → **Jetzt synchronisieren**
4. Auf GitHub prüfen: Commits da, unter *Tags* auch alle `v*`-Tags. Der Forgejo-Push-Mirror spiegelt alle Refs (Branches und Tags).

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
| Tag da, aber kein Release; GitHub → *Actions* → *Release* rot | Log lesen. Validierung rot: Fehler auf Forgejo beheben, **neue Version** releasen (Tags werden nie verschoben). Vorübergehender Fehler (Runner, Netz): *Re-run all jobs* |
| Workflow bricht mit „already exists“ ab | Release existiert schon, wird absichtlich nie überschrieben – nichts tun |
| SHA-256 GitHub ≠ Forgejo | GitHub-Release als *Pre-release* markieren (nicht löschen, Releases werden nie gelöscht), Ursache klären, Korrektur als neue Version |
