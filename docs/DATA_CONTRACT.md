# JobCLI resume and job data contract

## Version

- **Contract version:** `1.0` (document date aligned with application features in this repo).
- **Primary interchange format:** JSON (native `ResumeData` shape; JSONResume and flat JSON are accepted via [`ResumeAutoDetector`](../jobcli/core/synonym_resolver.py)).

## Native resume JSON (`ResumeData`)

Required:

- `personal.first_name`, `personal.last_name`, `personal.email`, `personal.phone`

Common optional blocks:

- `personal`: `address`, `city`, `state`, `country`, `zip_code`, `linkedin`, `github`, `portfolio`, `website`
- `experience[]`: `company`, `title`, `start_date`, `end_date`, `current`, `description`
- `education[]`: `school`, `degree`, `field_of_study`, `graduation_year`, `gpa`
- `work_authorization`: `authorized_to_work`, `require_sponsorship`, `visa_status`
- `demographics`: `gender`, `pronouns`, `sexual_orientation`, `race`, `veteran_status`, `disability_status`
- `skills[]`, `certifications[]`

### Derived hints (deterministic, not stored in JSON)

When explicit fields are empty, the CLI may **infer** conservative defaults for form matching only:

- **Country:** US when `state` is a US state code or city/state clearly indicate the United States (see [`derived_profile`](../jobcli/core/derived_profile.py)). Disable via config `infer_location_country: false`.
- **Pronouns:** from `gender` only when `pronouns` is unset and gender is unambiguous; never overrides explicit pronouns or “prefer not to say” style values.

The LLM prompt may include these as `_derived_hints` for transparency.

## Jobs (`Job`)

- `url` (required): canonical job application link; normalized on insert (tracking params stripped).
- `resolved_url` (optional): last known browser URL after redirects; updated during apply when it differs from `url`.

## Agent memory (SQLite)

Field answers are keyed by normalized labels (see [`SynonymResolver`](../jobcli/core/synonym_resolver.py)). Priority when filling: **resume JSON → ATS-specific memory → universal memory**.
