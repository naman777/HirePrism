# Phase 1 Assumptions And Observations

This document records what Phase 1 confirmed from the current raw snapshot in `data/raw/placements.json`. These are observations from the file as it exists today, not modeling decisions for later phases.

## Raw envelope

- The raw file is a top-level JSON object, not a bare list.
- The expected payload key is `placements`, and it contains 461 parent records.
- Those 461 parent records expand to 654 offer objects.
- `load_placements()` should validate the top-level object and the `placements` list before any downstream processing.

## Confirmed schema shape

- The stable parent-level keys are `_createdAt`, `companyName`, `id`, `noticeDate`, and `offers`.
- The raw file also contains top-level spillover fields: `branchesAllowed` and `eligibilityCgpa` appear on 98 parent records. This means Phase 2 flattening cannot assume a perfectly clean parent/offer boundary.
- Offer-level keys currently include:
  - `branchesAllowed`
  - `branchesNote`
  - `branchwiseBreakup`
  - `ctc`
  - `ctcNote`
  - `eligibilityCgpa`
  - `eligibilityNote`
  - `hasCTC`
  - `hasStipend`
  - `jobRole`
  - `stipend`
  - `stipendNote`
  - `studentsSelected`
  - `type`

## Confirmed formats

- Every current `noticeDate` value matches `DD/MM/YYYY`.
- Every current `_createdAt` value is a dict with `seconds` and `nanoseconds`.
- Offers per parent record are not uniform:
  - minimum: 1
  - maximum: 12
  - mean: 1.419
- Branch lists are multi-valued and irregular:
  - only 6 offers have no `branchesAllowed`
  - branch-list lengths range from 0 to 14 values

## Raw variation that matters later

- `jobRole` has 518 unique raw values across 654 offers.
- `ctc` has 212 unique raw values.
- `stipend` has 80 unique raw values.
- `studentsSelected` has 88 unique raw values.
- `eligibilityCgpa` has 30 unique raw values.
- `type` is relatively controlled at 6 raw values, but those values still mix internship, FTE, and conversion concepts.

## Compensation and stipend findings

- `ctc` is not clean numeric data.
  - 406 values are plain integers.
  - 135 are numeric ranges.
  - 68 are empty.
  - the remainder are pending, unknown, or free-text values such as `To be notified`, `Not Disclosed`, and `Will be communicated shortly`.
- `stipend` is also mixed-format.
  - 403 values are plain integers.
  - 48 are ranges.
  - 181 are empty.
  - the remainder include unknown and non-standard text values.
- Phase 3 should keep raw compensation text and parse into separate normalized/status columns rather than overwrite the originals.

## Note-field signal

- Notes are common enough to matter:
  - `ctcNote`: 399 offers, 61.01%
  - `stipendNote`: 148 offers, 22.63%
  - `branchesNote`: 97 offers, 14.83%
  - `eligibilityNote`: 103 offers, 15.75%
- `ctcNote` contains high-value structured hints such as location, gross salary details, monthly/annual breakdowns, and work mode.
- Note extraction should be high priority in later phases because a meaningful share of compensation context is not in the main scalar fields.

## Risks For Phase 2 And Phase 3

- Parent-level spillover fields (`branchesAllowed`, `eligibilityCgpa`) need a deterministic flattening rule before the analytical schema is built.
- Compensation parsing must handle integers, ranges, empty strings, pending text, unknown text, and non-standard free text.
- Role normalization will be high effort because raw role strings are extremely fragmented relative to dataset size.
- Selection status and eligibility values mix numeric and descriptive text, so they should not be forced directly into numeric columns.
- `branchwiseBreakup` is present on some offers and missing on many others, so later modeling should treat it as optional semi-structured detail, not as a guaranteed field.
