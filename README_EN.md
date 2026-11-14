# Steam Achievement Translation Library

[简体中文](README.md) | English

A community-maintained library of Steam achievement translations, with game search, multilingual text previews, and downloads. Find a translation, request one, or contribute your own.

<p align="center">
  <a href="https://gaboron.github.io/steam-achievement-translation-library/?lang=en"><img alt="Browse the translation library" src="https://img.shields.io/badge/Browse%20Library-Open%20Website-1f6feb?style=for-the-badge&amp;logo=steam&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/SATLI"><img alt="View the translation manager" src="https://img.shields.io/badge/Translation%20Manager-Windows-0078D4?style=for-the-badge&amp;logo=windows11&amp;logoColor=white"></a>
  <a href="https://github.com/GaBoron/steam-achievement-localizer-skill"><img alt="Create a translation with the translation Skill" src="https://img.shields.io/badge/Translation%20Skill-Create%20Translation-412991?style=for-the-badge&amp;logo=openai&amp;logoColor=white"></a>
  <a href="docs/CONTRIBUTING_EN.md"><img alt="Read the submission guide" src="https://img.shields.io/badge/Contribute-Submission%20Guide-2DA44E?style=for-the-badge&amp;logo=github&amp;logoColor=white"></a>
</p>

## 🚀 Find And Use A Translation

1. Search the [library website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en) by game name, Steam App ID, or contributor, or filter by status and language.
2. Open the game details, choose a variant for your game version, preview the target language, and check for “Possibly outdated” or “May not work” status.
3. Choose a compatible client for the file type. Each website download lists supported clients and their minimum versions.

| Your task | Tool |
| --- | --- |
| Download and display JSON translations in the Steam interface | [SATLI lite](https://github.com/GaBoron/SATLI-lite), requiring Millennium 3.5.0+; usable independently of SATLI |
| Manage local BIN files on Windows, edit, install, back up, restore, or export submission ZIPs | [Steam Achievement Translation Manager (SATLI)](https://github.com/GaBoron/SATLI) |

Standalone format 2 JSON requires SATLI lite 0.2.0+. JSON supplies display text and cannot be installed as BIN; changing the extension does not convert it. Before using a BIN, confirm the App ID and back up the original through the manager. Results depend on the game, Steam, and client support.

## 🤝 Request, Contribute, Or Report

- **Missing translation:** Open a [translation petition](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_en.yml) with an App ID, game name, and target Steam language codes. An original schema ZIP is optional. When public data is available, automation provides a JSON draft to translate.
- **Translation to share or update:** Follow the [contribution guide](docs/CONTRIBUTING_EN.md) to prepare standalone JSON or a BIN ZIP and choose the new-submission or update form. You normally do not need to fork the repository.
- **Possibly outdated or ineffective file:** Submit a [file issue report](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml). Submit an update directly if you have a correction.

Create translations with SATLI or the [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill), which provides a research, translation, and validation workflow.

For a standalone visual editor, see [PanVena/SteamAchievementLocalizer](https://github.com/PanVena/SteamAchievementLocalizer).

## 🧩 Integration And Development

The public interface consists of `index-v2.json` and the BIN/JSON files it references, available anonymously.

- [Data integration](docs/integration.md#english): catalog fields, pinned snapshots, download validation, and a client example.
- [Translation JSON format](docs/translation-json.md#english): format contracts, standalone submissions, and draft generation.
- [Development and maintenance](docs/development.md#english): code responsibilities, submission automation, and validation entry points.
- [Website maintenance](docs/website.md#english): local previews, frontend modules, and Pages deployment.

## 📈 Library Statistics

![Library growth and contributor ranking](docs/statistics/library-statistics.svg)

## 💬 Support

For help, email [SATLI.support@proton.me](mailto:SATLI.support@proton.me).

## ⚖️ License And Rights

See [LICENSE.md](LICENSE.md). Website and workflow scripts use MIT; contributor-owned translation portions use CC BY 4.0; original game content, achievement text, and Steam schema data remain the property of their respective rights holders.
