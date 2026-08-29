# Contributing

Thank you for contributing to the Steam Achievement Translation Library. After you submit an issue form, automation validates the attachment and creates a review PR; you normally do not need to fork the repository.

## 🧰 1. Prepare A Translation

These tools can produce files in the expected submission format:

- 🖥️ [Steam Achievement Translation Manager](https://github.com/GaBoron/steam-achievement-translation-installer): a visual local editor that exports standard BIN files and submission ZIP files.
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill): researches, translates, and validates files with Codex; completed files are written to the project's `final/` directory.

Other editors are also supported, but every submission must meet these requirements:

| Check | Requirement |
| --- | --- |
| Steam app ID | Matches the number in both file names; automation derives the store URL from it |
| BIN name | `UserGameStatsSchema_<app_id>.bin` |
| ZIP name | `UserGameStatsSchema_<app_id>.zip` |
| Single-version ZIP | Contains only the matching BIN at its root |
| Languages | Detected automatically from the schema; for each achievement, names and descriptions are checked independently and each field must either contain text in every detected language or be empty in every detected language |
| Game name | Uses the Steam store name; a Chinese translation may follow the original name when useful |

Search [INDEX_EN.md](INDEX_EN.md) by app ID first to determine whether you are submitting a new game or updating an accepted entry.

> [!NOTE]
> The repository is currently in a parallel V1/V2 migration period. Contributors still upload one ZIP; automation generates both authoritative V2 data and V1 compatibility data. See the [V2 migration status in the README](README_EN.md#-v2-migration-status) for the deadline and legacy-format removal schedule.

## 🧭 2. Choose A Submission

| Situation | Entry |
| --- | --- |
| 💬 You only have the original Steam schema and want a translation | [Translation petition](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_en.yml) |
| ➕ Your translation is complete and the app ID is not indexed | [Submit a new translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_en.yml) |
| 🔄 Your translation is complete and the app ID is already indexed | [Update an accepted translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_en.yml) |
| ⚠️ A file may be outdated or ineffective, but you have no replacement | [Report a file issue](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml) |

A petition records demand only; its untranslated schema is not added to the library. For an update, briefly describe the added, removed, or changed content.

## 📤 3. Submit And Correct

1. Complete the matching issue form and attach the ZIP.
2. Wait for checks covering file structure, Binary KeyValues roundtrip, achievement IDs, and language coverage.
3. After validation passes, automation creates a PR and requests maintainer review.

Follow the bot's comment when validation fails. While the source issue is open, you can edit its form values. After a PR is created, use a PR comment:

| Command | Purpose |
| --- | --- |
| `/update doc` plus a ZIP attachment | Replace the submitted file or complete multi-version package |
| `/update doc <variant_id>` plus a ZIP attachment | Replace one existing variant |
| `/update id` or `name` plus a new value | Change the app ID or game name; changing the app ID also regenerates the store URL |
| `/update summary <summary>` | Change the summary for an accepted-file update |
| `/force-refresh` | Retry all checks when the content is correct but automation state is stale |

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
- A full update resubmits the complete version set. To replace one existing variant, enter its ID in the update form and upload a normal single-version ZIP.
- Languages and achievement counts are detected for each variant independently and may differ when the variants target different game versions.

## ✅ Automated Checks

Automation derives the store URL from the app ID and checks ZIP safety and size, Binary KeyValues parsing and byte-identical roundtrip, unique achievement IDs, automatically detected language coverage, and update differences. Submit only translations you are allowed to share.

For workflow, script, manifest, generated index, or `files/` changes, run from the repository root:

```bash
python -m compileall -q workflow-scripts
python workflow-scripts/check_repository.py
```

See [LICENSE.md](LICENSE.md) for rights and contribution terms.
