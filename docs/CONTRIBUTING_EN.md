# Contributing

Thank you for contributing to the Steam Achievement Translation Library. After you submit an issue form, automation validates the attachment and creates a review PR; you normally do not need to fork the repository.

## 🧰 1. Prepare A Translation

These tools can produce files in the expected submission format:

- 🖥️ [Steam Achievement Translation Manager](https://github.com/GaBoron/SATLI): a visual local editor that exports standard BIN files and submission ZIP files.
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill): researches, translates, and validates files; completed files are written to the project's `final/` directory.

Submit [standalone format 2 JSON](translation-json.md#standalone-json-format-2) directly, or continue using BIN ZIPs. Format 1 JSON exported by tools such as SATLI lite requires the format 2 source snapshot and target-language fields before standalone submission; changing the version alone is insufficient. Existing SATLI lite supports format 1 only; format 2 requires updated client support.

Other editors are also supported, but every submission must meet these requirements:

| Check | Requirement |
| --- | --- |
| Steam app ID | Matches JSON/BIN content and attachment filenames; automation derives the store URL from it |
| Standalone JSON | `UserGameStatsSchema_<app_id>.json`, format 2 with completed translations and no active `draft`; no BIN or ZIP required |
| BIN name | `UserGameStatsSchema_<app_id>.bin` |
| ZIP name | `UserGameStatsSchema_<app_id>.zip` |
| Single-version ZIP | Contains only the matching BIN or format 2 JSON at its root |
| Languages | Detected from the BIN or JSON; for each achievement, names and descriptions are checked independently and each field must either contain text in every detected language or be empty in every detected language |
| Game name | Uses the Steam store name; a Chinese translation may follow the original name when useful |

Search the [library website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en) by app ID first to determine whether you are submitting a new game or updating an accepted entry.

## 🧭 2. Choose A Submission

| Situation | Entry |
| --- | --- |
| 💬 You want a translation, with or without original files | [Translation petition](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_en.yml) |
| ➕ Your translation is complete and the app ID is not indexed | [Submit a new translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_en.yml) |
| 🔄 Your translation is complete and the app ID is already indexed | [Update an accepted translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_en.yml) |
| ⚠️ A file may be outdated or ineffective, but you have no replacement | [Report a file issue](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml) |

Petitions require only an app ID, game name and target languages; attachments are optional and untranslated schemas are not added to the library. Available public data produces a JSON draft with blank target fields; unavailable data leaves the petition open awaiting a source. See [downloads and local generation](translation-json.md#standalone-json-format-2). For an update, briefly describe the added, removed, or changed content.

## 📤 3. Submit And Correct

1. Complete the matching issue form and attach standalone JSON or a ZIP.
2. Wait for checks covering file structure, API names, source records and language coverage; BIN submissions also require Binary KeyValues roundtrip.
3. After validation passes, automation creates a PR and requests maintainer review.

Follow the bot's comment when validation fails. While the source issue is open, you can edit its form values. After a PR is created, use a PR comment:

| Command | Purpose |
| --- | --- |
| `/update doc` plus a JSON or ZIP attachment | Replace the submitted file or complete multi-version package |
| `/update doc <variant_id>` plus a JSON or ZIP attachment | Replace one existing variant |
| `/update id` or `name` plus a new value | Change the app ID or game name; changing the app ID also regenerates the store URL |
| `/update summary <summary>` | Change the summary for an accepted-file update |
| `/force-refresh` | Resync with the base branch, refresh current schema metadata and achievement review tables, and retry checks when automation state is stale |

> [!IMPORTANT]
> Put the command and attachment in the same comment. Only the original issue author, contributors listed in the PR, or maintainers can modify a submission. The bot's response is the source of truth for a specific error and its available commands.

## 🗂️ Multiple Versions For One Game

If one app ID needs multiple independently usable schemas, put the complete version set in one ZIP and add `translation-variants.json` at the root:

```text
UserGameStatsSchema_123456.zip
├── translation-variants.json
├── UserGameStatsSchema_123456.bin
└── branch-name/
    └── UserGameStatsSchema_123456.bin
```

```json
{
  "variants": {
    "default": {
      "label": {
        "zh": "正式分支",
        "en": "Stable branch"
      }
    },
    "branch-name": {
      "label": {
        "zh": "测试分支",
        "en": "Beta branch"
      },
      "description": {
        "zh": "适用于游戏的公开测试分支",
        "en": "For the game's public beta branch"
      }
    }
  }
}
```

- A package supports 1–16 variants and must contain `default`. Each object key is the variant ID, and `default` is the default choice.
- Other variant IDs use lowercase letters, numbers, and hyphens only, and match their subdirectory names. File paths are derived from the IDs and must not be declared in the manifest.
- Every variant needs a short bilingual `label`. Add a bilingual `description` only when its compatibility or purpose needs more explanation.
- Do not declare a format version, `primary`, file paths, hashes, sizes, achievement counts, languages, app IDs, contributors, timestamps, or Issue/PR data; automation derives them. Two variants cannot contain identical files.
- A full update resubmits the complete version set. To replace one existing variant, enter its ID in the update form and upload standalone JSON or a normal single-version ZIP.
- Each variant may contain a BIN or format 2 JSON; use the same layout with `.json` instead of `.bin` for JSON variants. Do not upload both for a variant: the bot generates BIN-derived format 1 JSON. JSON `variant_id` must match its directory.
- Languages and achievement counts are detected for each variant independently and may differ when the variants target different game versions.

## ✅ Automated Checks

Automation derives the store URL from the app ID and checks attachment safety and size, source records, achievement IDs and language coverage; BIN files also require byte-identical Binary KeyValues roundtrip. Submit only translations you are allowed to share.

Each variant is stored under `files/<app_id>/<variant_id>/` with a BIN and generated format 1 JSON, or standalone format 2 JSON only. Do not edit generated format 1 files; format 2 uploads are strictly validated and canonicalized. Automation generates `achievements.md` in each variant directory for review directly in the PR's **Files changed**. Text is grouped by achievement and field, with neighboring languages and one field per line. Updates include only changed achievements and show before/after values. Publication automatically recycles review files. Preview published text on the [website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en).

Each review PR changes only its game's directory, with pending catalog metadata in generated `submission.json`. Checks strictly compare metadata with BIN/JSON content. After merge, automation collects pending games on main, updates `index-v2.json`, statistics, and the website, and recycles published `submission.json` files. Different games can be reviewed independently; content conflicts within one game require maintainer resolution. `/force-refresh` merges main while preserving submission history; BIN app ID corrections apply only to new, unpublished games. Standalone JSON embeds its ID and source, which cannot be rewritten automatically; close an incorrect submission and resubmit corrected JSON.

An update submission or `/update doc` can upgrade a JSON-only variant with a real BIN while retaining its variant ID, contributors and first submission time. The BIN must preserve accepted target-language text; automation then generates format 1 JSON. An existing BIN variant cannot be replaced by standalone JSON; add another variant to keep both. Valid display JSON does not certify Steam client BIN compatibility.

Windows maintenance requires `pywin32`; Linux requires working `gio trash`. Files remain in place with an exact-path error when recycling is unavailable.

For workflow, script, catalog, generated data, or `files/` changes, run from the repository root:

```bash
python -m compileall -q workflow-scripts
python workflow-scripts/check_repository.py
```

See the [data integration guide](integration.md#english) for client interfaces and [website maintenance](website.md#english) for builds, local previews, and GitHub Pages configuration.

See [LICENSE.md](../LICENSE.md) for rights and contribution terms.
