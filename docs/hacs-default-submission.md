# HACS-Standard-Store – Antrag vorbereiten (noch nicht stellen)

Stand der Prüfung: 2026-10-12, Quellen: hacs.xyz/docs/publish/start, …/integration, …/include, Repo `hacs/default` (PR-Vorlage, Skripte), `home-assistant/brands` README, developers.home-assistant.io (brand_images, manifest).

## Checkliste

| Anforderung | Quelle | Status |
| --- | --- | --- |
| Öffentliches GitHub-Repo | publish/start: „Only public repositories on GitHub will work with HACS.“ | offen (Spiegel anlegen) |
| Repo-Beschreibung | publish/start | offen, Text unten |
| Topics | publish/start | offen, Liste unten |
| Issues aktiviert | include (Check „repository“) | offen |
| Nicht archiviert | include (Check „archived“) | – |
| README mit Bedienung | publish/start | erledigt (`README.md`) |
| `hacs.json` im Root mit `name` | publish/start | erledigt |
| Eine Integration unter `custom_components/<domain>/` | publish/integration | erledigt |
| Manifest: domain, documentation, issue_tracker, codeowners, name, version | publish/integration | erledigt (Platzhalter ersetzen) |
| Brand-Assets: `custom_components/repo_installer/brand/icon.png` | publish/integration, include (Check „brands“) | erledigt (`icon.png` 256 px, `icon@2x.png` 512 px) |
| HACS-Action grün, **ohne** `ignore` | include, PR-Vorlage | offen (läuft erst nach Spiegelung; Repo-Prüfungen brauchen Beschreibung, Topics, Issues) |
| hassfest-Action grün | include | lokal grün, auf GitHub offen |
| Mindestens ein **echtes Release** (nicht nur Tag), erstellt **nach** grünen Actions | include, PR-Vorlage | offen |
| PR aus persönlichem Account (editierbar), Branch von `master` | include | beim Antrag |
| `country` nur bei länderbezogenen Repos | include | entfällt |

Hinweis Policy: Ausgeschlossen werden laut include.md nur „Custom integrations used for alpha or beta testing core integrations, or those that override core integrations“. Eine Regel gegen Integrationen, die selbst Integrationen installieren, wurde in hacs/documentation und hacs/default nicht gefunden – die Aufnahme liegt trotzdem im Ermessen der Maintainer („drafted for minor issues, and closed for major issues“). Deshalb die Vorab-Anfrage.

## Textvorschläge

**Beschreibung:**
> Install and update Home Assistant custom integrations from GitHub, GitLab, Forgejo and Gitea releases – a self-hosted complement to HACS.

**Topics:** `home-assistant`, `hacs`, `hacs-integration`, `custom-integration`, `forgejo`, `gitea`, `gitlab`, `self-hosted`

## Antragsablauf

1. Vorab-Anfrage stellen (unten), Antwort abwarten.
2. Voraussetzungen der Checkliste erfüllt, letzte Actions grün, danach ein neues Release.
3. `hacs/default` forken (persönlicher Account), Branch von `master` anlegen.
4. Datei `integration` (JSON-Liste `"owner/repo"`) – `"<GITHUB_USER>/repo_installer"` **alphabetisch** einsortieren (Prüfung: `sorted(..., key=str.casefold)`), nicht ans Ende.
5. Pull-Request mit vollständig ausgefüllter Vorlage:
   - alle Haken der Checkliste
   - Link zum aktuellen Release
   - Link zum grünen HACS-Action-Lauf (ohne `ignore`)
   - Link zum grünen hassfest-Lauf
6. Keine Reviews anfordern (Vorlage: sonst wird der PR geschlossen). Abwarten.

## Vorab-Anfrage (Entwurf, englisch)

Für HACS Discord (#publishing o. ä.) oder GitHub Discussions von `hacs`:

> Hi! Before opening a PR to hacs/default I'd like to ask whether this kind of integration would be acceptable as a default repository.
>
> **Repo Installer** (https://github.com/<GITHUB_USER>/repo_installer) installs and updates custom integrations from release ZIPs on **self-hosted** Git servers – Forgejo, Gitea, GitLab – and GitHub. Typical use: your own integrations or forks living on a home-lab Forgejo, which HACS can't reach because it only supports GitHub.
>
> It is meant to complement HACS, not replace it: no store, no index, no discovery – the user enters one repository URL per integration. Every install requires a SHA-256 from the release notes, downloads are bound to the repository host, nothing downloaded is executed, and Home Assistant is never restarted automatically. The README tells users to remove an integration from HACS before managing it with Repo Installer, so the two never fight over the same folder.
>
> Is an integration that installs other integrations within scope for the default store, or would you prefer it to stay a custom repository? Thanks!

## Empfehlung

Erst die Antwort auf die Vorab-Anfrage abwarten. Bei Ablehnung bleibt der Weg über „benutzerdefiniertes Repository“ voll nutzbar; der Aufwand für den Antrag entfällt dann.
