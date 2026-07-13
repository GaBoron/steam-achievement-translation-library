# Steam Achievement Translation Library

[简体中文](README.md) | English

This project is a **Steam achievement translation data repository**. It collects community-submitted `UserGameStatsSchema_<app_id>.bin` translation files and maintains searchable indexes, issue templates, and automated first-review workflows.

> - To find, install, and restore existing translations on Windows, use [Steam Achievement Translation Installer](https://github.com/GaBoron/steam-achievement-translation-installer) **(Recommended for most users)**
> - To create or review translations with an AI skill, visit [GaBoron/steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill)
> - To perform localization manually using local software, please visit [PanVena/SteamAchievementLocalizer](https://github.com/PanVena/SteamAchievementLocalizer)  
> This repository stores only the translation data and the data submission process.

## Quick Links

| Task | Where to go |
| --- | --- |
| Find a translation | Open [the library index](INDEX_EN.md) and search by Steam app ID, game name, contributor, or language code |
| Install an existing translation | Download [Steam Achievement Translation Installer](https://github.com/GaBoron/steam-achievement-translation-installer/releases/latest) to scan, install, and safely restore translations |
| Submit a new game | Use the ["Submit Steam achievement translation"](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_en.yml) issue template |
| Update an accepted file | Use the ["Update existing Steam achievement translation"](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_en.yml) issue template |
| Report an outdated file | Use the ["Report outdated achievement file"](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml) issue template |
| Read contribution rules | See [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md) |
| Feature Request | Use the [“Feature petition”](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=feature_petition_en.yml) issue template |

## Usage Flow

### 1. Find The Game

Prefer the Steam app ID. Open the game's Steam store page; the number after `/app/` is the app ID. For example, `https://store.steampowered.com/app/123456/...` maps to `123456`.

Open [the library index](INDEX_EN.md), then search with your browser or GitHub page search:

| Search term | Best use |
| --- | --- |
| Steam app ID | Most accurate; use this first when possible |
| Game name | Use when you do not know the app ID; some entries include both original and Chinese names |
| Language code | For example `schinese`, `tchinese`, or `japanese` |
| Contributor | Use when checking files submitted by a specific contributor |

After finding a row, check both Status and Last updated. If the status is possibly outdated, someone has reported that the Steam schema may have changed. Unless you know the file still applies, wait for an update PR before downloading.

A game may provide multiple versions. In that case, the File column shows multiple links with English version notes. Choose the file matching your game branch or use case; the filenames alone do not distinguish variants.

### 2. Download The File

Prefer clicking `UserGameStatsSchema_<app_id>.bin` in the File column. The index uses jsDelivr as the main download entry and points to the matching file on the current `main` branch.

After downloading, check:

| Check | Why it matters |
| --- | --- |
| File name | It should stay `UserGameStatsSchema_<app_id>.bin`, not `.txt`, `.html`, or an extra-suffixed file |
| App ID | The number in the file name must match the game you are replacing |
| File size | Compare it with the size shown in the index File column; if the size is clearly wrong, do not replace your local file |

If an index download link does not work, open the repository's `files/<app_id>/` directory, find the matching `UserGameStatsSchema_<app_id>.bin` by game app ID, and download it manually.

### 3. Find The Local Steam File

The local Steam schema is usually under the Steam install directory:

```text
<Steam install directory>/appcache/stats/UserGameStatsSchema_<app_id>.bin
```

Common Windows locations:

```text
C:/Program Files (x86)/Steam/appcache/stats/UserGameStatsSchema_<app_id>.bin
C:/Program Files/Steam/appcache/stats/UserGameStatsSchema_<app_id>.bin
```

This file is usually not inside the game install folder and not under `steamapps/common/<game name>`. Custom Steam library folders usually do not change the `appcache/stats` location.

If you cannot find it:

1. Start Steam.
2. Start the game once and reach the achievement or main-menu flow so Steam can create or refresh the schema cache.
3. Close the game and Steam.
4. Search the Steam install directory for `UserGameStatsSchema_<app_id>.bin`.

You can also use the helper from [steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill):

```bash
python scripts/steam_bkv_tool.py find-schema --game-id <app_id>
```

### 4. Replace And Use

Before replacing anything, close Steam and the game, then back up the original file, for example:

```text
UserGameStatsSchema_<app_id>.bin.bak
```

Place the downloaded `UserGameStatsSchema_<app_id>.bin` into the local `appcache/stats` directory and overwrite the matching file. Make sure the file name is exactly the same, then restart Steam and the game.

Steam may regenerate this file after a game update, Steam cache refresh, or achievement schema change. If translations stop working, achievements are missing, or the index entry looks stale, use the outdated-report issue template. If you already have a new file, use the update template instead.

## License And Rights

This repository uses a mixed rights notice. See [LICENSE.md](LICENSE.md). In short: workflow scripts are provided under MIT; contributor-owned translation portions are licensed under CC BY 4.0; original game content, achievement text, Steam schema content, and related files remain the property of their respective rights holders.
