# Steam Achievement Translation Library

[简体中文](README.md) | English

This project is a **Steam achievement translation data repository**. It collects community-submitted `UserGameStatsSchema_<app_id>.bin` translation files and maintains searchable indexes, issue templates, and automated first-review workflows.

> Translation scripts, the Codex skill, installation guidance, and local application workflows are maintained in [GaBoron/steam-achievement-localizer-skill](https://github.com/GaBoron/steam-achievement-localizer-skill). This repository hosts translation data and contribution automation.

## Quick Links

| Task | Where to go |
| --- | --- |
| Find a translation | Open [the library index](INDEX_EN.md) and search by Steam app ID, game name, contributor, or language code |
| Submit a new game | Use the "Submit Steam achievement translation" issue template |
| Update an accepted file | Use the "Update existing Steam achievement translation" issue template |
| Report an outdated file | Use the "Report outdated achievement file" issue template |
| Read contribution rules | See [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md) |

## Usage Notes

Before downloading, check the index Status and Last updated columns. If a game is marked as possibly outdated, someone has reported that the Steam schema may have changed.

After downloading a `UserGameStatsSchema_<app_id>.bin` file, apply it with a local tool you trust. Back up your local Steam file before replacing anything.

## License And Rights

This repository uses a mixed rights notice. See [LICENSE.md](LICENSE.md). In short: workflow scripts are provided under MIT; contributor-owned translation portions are licensed under CC BY 4.0; original game content, achievement text, Steam schema content, and related files remain the property of their respective rights holders.
