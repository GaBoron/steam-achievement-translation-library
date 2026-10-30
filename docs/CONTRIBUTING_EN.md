# Contributing

[Home](../README_EN.md) · [简体中文](CONTRIBUTING.md)

Share translations through an issue form. Automation validates the attachment and creates a PR for maintainer review; you normally do not need to fork the repository. Submit only content you may share. See [LICENSE.md](../LICENSE.md) for contribution terms.

## 🧭 1. Choose An Entry

Search the [library website](https://gaboron.github.io/steam-achievement-translation-library/?lang=en) and [open PRs](https://github.com/GaBoron/steam-achievement-translation-library/pulls) by App ID first to avoid duplicate submissions.

| Situation | Entry |
| --- | --- |
| You want a translation, with or without original files | [Translation petition](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_en.yml) |
| Your translation is complete, the App ID is not indexed, and no submission is under review | [Submit a new translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_en.yml) |
| Your translation is complete and the App ID is already indexed | [Update an accepted translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_en.yml) |
| A translation may be outdated or ineffective, but you have no replacement | [Report a file issue](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml) |

Petitions need an App ID, game name, and target Steam language codes; an original schema ZIP is optional. When public data is available, automation provides a JSON draft with blank target fields. Failed acquisition keeps the petition open awaiting a source. See [draft downloads and local generation](translation-json.md#generate-a-candidate). A petition is not a completed translation and is not published directly.

## 🧰 2. Prepare A Translation

These tools can produce files in the expected submission format:

- 🖥️ [Steam Achievement Translation Manager](https://github.com/GaBoron/SATLI): a visual local editor that exports standard BIN files and submission ZIP files.
- 🤖 [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill): researches, translates, and validates files; completed files are written to the project's `final/` directory.

Upload [standalone format 2 JSON](translation-json.md#english) directly, or a ZIP containing BIN or JSON. See that guide for format distinctions, conversion of format 1 text for independent submission, and text limits.

Other editors are also supported, but every submission must meet these requirements:

| Check | Requirement |
| --- | --- |
| Steam app ID | Matches JSON/BIN content and attachment filenames; automation derives the store URL from it |
| Standalone JSON | `UserGameStatsSchema_<app_id>.json`, format 2 with complete coverage for declared languages; no BIN or ZIP required |
| BIN name | `UserGameStatsSchema_<app_id>.bin` |
| ZIP name | `UserGameStatsSchema_<app_id>.zip` |
| Single-version ZIP | Contains only the matching BIN or format 2 JSON at its root |
| Size | At most 32 MiB per attachment and per BIN/JSON; at most 64 MiB of uncompressed schema data in a multi-version ZIP |
| Languages | Detected from the BIN or JSON; for each achievement, names and descriptions are checked independently and each field must either contain text in every detected language or be empty in every detected language |
| Game name | Uses the Steam store name; a Chinese translation may follow the original name when useful |

Use the notes for sources, terminology, and actual test results. Updates also need a summary of added, removed, or changed content. Passing structural checks must not be presented as confirmation that a file works in Steam.

## 📤 3. Submit And Correct

1. Complete the matching issue form and attach standalone JSON or a ZIP.
2. Wait for attachment structure, API name, and language coverage checks. BIN files also require a byte-identical Binary KeyValues roundtrip; format 2 JSON is canonicalized before storage.
3. After validation, automation creates a PR and closes and locks the source issue. Maintainers review the notes and achievement comparison. After merge, automation publishes the catalog and website.

Follow the bot's response when validation fails. While the source issue is open, edit its field values while preserving the `###` field headings. After a PR is created, comment on that PR:

| Command | Purpose |
| --- | --- |
| `/update doc` plus a JSON or ZIP attachment | Replace the submitted file or complete multi-version package |
| `/update doc <variant_id>` plus a JSON or ZIP attachment | Replace one existing variant |
| `/update id <App ID>` | Correct the ID of a new, unpublished game; an accepted-game update cannot change its ID |
| `/update name <game name>` | Change the game name |
| `/update summary <summary>` | Change the summary for an accepted-file update |
| `/force-refresh` | Resync with the base branch, refresh current schema metadata and achievement review tables, and retry checks when automation state is stale |

> [!IMPORTANT]
> Put the command and attachment in the same comment. Only the original issue author, contributors listed in the PR, or maintainers can modify a submission. The bot's response is the source of truth for a specific error and its available commands.

Review generated `achievements.md` files in the PR's **Files changed**. Languages appear together by achievement and field; updates show changed achievements and before/after values. These files are removed after publication; published text can be previewed on the website. File validation does not judge translation quality or replace real Steam verification.

## 🗂️ Multiple Versions For One Game

For translations targeting different game branches or versions under one App ID, put the complete set in a ZIP with `translation-variants.json` at the root. Each translation already contains its languages; separate variants are not needed for each language.

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
- Variant IDs match `[a-z0-9][a-z0-9-]{0,63}`; non-default IDs match their subdirectories. File paths are derived from the IDs and must not be declared in the manifest.
- Every variant needs a short bilingual `label`. Add a bilingual `description` only when its compatibility or purpose needs more explanation.
- Do not declare a format version, `primary`, file paths, hashes, sizes, achievement counts, languages, app IDs, contributors, timestamps, or Issue/PR data; automation derives them. Two variants cannot contain identical files.
- A full update resubmits the complete version set. To replace one existing variant, enter its ID in the update form and upload standalone JSON or a normal single-version ZIP.
- Each variant may contain a BIN or format 2 JSON; use the same layout with `.json` instead of `.bin` for JSON variants. Do not upload both for a variant: the bot generates BIN-derived format 1 JSON. JSON `variant_id` must match its directory.
- Languages and achievement counts are detected for each variant independently and may differ when the variants target different game versions.

## 🔄 Format Restrictions On Updates

An update submission or `/update doc` can upgrade a JSON-only variant with a real BIN while retaining its variant ID, contributors, and first submission time. The BIN must preserve accepted text in every declared language; automation then generates format 1 JSON. An existing BIN variant cannot be replaced by standalone JSON; add another variant to keep both. Submissions identical to accepted files are rejected.

For repository scripts, workflows, and publication maintenance, see [development and maintenance](development.md#english). For client consumption, see [data integration](integration.md#english).
