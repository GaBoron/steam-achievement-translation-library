# Contributing

Thank you for contributing to the Steam Achievement Translation Library. After you submit an issue form, automation validates the attachment and creates a review PR; you normally do not need to fork the repository.

## 1. Prepare A Translation

These tools can produce files in the expected submission format:

- [Steam Achievement Translation Manager](https://github.com/GaBoron/steam-achievement-translation-installer): a visual local editor that exports standard BIN files and submission ZIP files.
- [Steam Achievement Localizer Skill](https://github.com/GaBoron/steam-achievement-localizer-skill): researches, translates, and validates files with Codex; completed files are written to the project's `final/` directory.

Other editors are also supported, but every submission must meet these requirements:

| Check | Requirement |
| --- | --- |
| Steam app ID | Matches the store URL and the number in both file names |
| BIN name | `UserGameStatsSchema_<app_id>.bin` |
| ZIP name | `UserGameStatsSchema_<app_id>.zip` |
| Single-version ZIP | Contains only the matching BIN at its root |
| Languages | Lists every Steam language with complete names and descriptions, separated by half-width commas |
| Game name | Uses the Steam store name; a Chinese translation may follow the original name when useful |

Search [INDEX_EN.md](INDEX_EN.md) by app ID first to determine whether you are submitting a new game or updating an accepted entry.

## 2. Choose A Submission

| Situation | Entry |
| --- | --- |
| You only have the original Steam schema and want a translation | [Translation petition](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_petition_en.yml) |
| Your translation is complete and the app ID is not indexed | [Submit a new translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_contribution_en.yml) |
| Your translation is complete and the app ID is already indexed | [Update an accepted translation](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=translation_update_en.yml) |
| A file may be outdated or ineffective, but you have no replacement | [Report a file issue](https://github.com/GaBoron/steam-achievement-translation-library/issues/new?template=outdated_report_en.yml) |

A petition records demand only; its untranslated schema is not added to the library. For an update, briefly describe the added, removed, or changed content.

## 3. Submit And Correct

1. Complete the matching issue form and attach the ZIP.
2. Wait for checks covering file structure, Binary KeyValues roundtrip, achievement IDs, and language coverage.
3. After validation passes, automation creates a PR and requests maintainer review.

Follow the bot's comment when validation fails. While the source issue is open, you can edit its form values. After a PR is created, use a PR comment:

| Command | Purpose |
| --- | --- |
| `/update doc` plus a ZIP attachment | Replace the submitted file or complete multi-version package |
| `/update doc <variant_id>` plus a ZIP attachment | Replace one existing variant |
| `/update id`, `name`, `store`, or `languages` plus a new value | Change that field; `languages` replaces the complete language list |
| `/update summary <summary>` | Change the summary for an accepted-file update |
| `/force-refresh` | Retry all checks when the content is correct but automation state is stale |

Put the command and attachment in the same comment. Only the original issue author, contributors listed in the PR, or maintainers can modify a submission. The bot's response is the source of truth for a specific error and its available commands.

## Multiple Versions For One Game

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
  "version": 1,
  "variants": [
    {
      "variant_id": "default",
      "primary": true,
      "file": "UserGameStatsSchema_123456.bin",
      "note_zh": "原版",
      "note_en": "Original"
    },
    {
      "variant_id": "branch-name",
      "primary": false,
      "file": "branch-name/UserGameStatsSchema_123456.bin",
      "note_zh": "分支版本",
      "note_en": "Branch version"
    }
  ]
}
```

- A package supports 1–16 variants and must have exactly one `primary: true` entry named `default`.
- Other `variant_id` values use lowercase letters, numbers, and hyphens only, and match their subdirectory names.
- Every variant needs short Chinese and English notes; two variants cannot contain identical files.
- A full update resubmits the complete version set. To replace one existing variant, enter its ID in the update form and upload a normal single-version ZIP.
- The form's language list applies to every variant and cannot be changed by a targeted variant update.

## Automated Checks

Automation checks the app ID and store URL, ZIP safety and size, Binary KeyValues parsing and byte-identical roundtrip, unique achievement IDs, language coverage, and update differences. Submit only translations you are allowed to share.

For workflow, script, index, or `files/` changes, run from the repository root:

```bash
python -m compileall -q workflow-scripts tests
python -m unittest discover -s tests -v
python workflow-scripts/check_repository.py
```

See [LICENSE.md](LICENSE.md) for rights and contribution terms.
