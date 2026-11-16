# Management reports

What the monthly Reports screen shows, how each figure is defined, how the files are tracked, and what it cannot do. Overtime follows the work rules in `docs/operations/DRIVER_WORK_RULES.md`.

## Planned figures, not hours worked

Every figure comes from the latest publication of each service day, urgent changes and recorded delays included. The software has no clock-in or GPS, so hours actually worked are not available. The screen, the Excel file and the PDF all carry the statement «Προγραμματισμένα στοιχεία από δημοσιευμένα προγράμματα» / "Planned figures from published schedules".

## Who can see it

The sidebar entry «Αναφορές» / "Reports" and the three API routes need `reports.read`. The `admin` and `management` roles hold it. Other roles get 403. Each organization sees only its own data.

## The screen

A month picker (default: the previous month), the Excel and PDF buttons, the last-export line, then three sections:

| Section | Rows | Order |
|---|---|---|
| Overtime against the yearly limit | Every active driver, plus inactive drivers with overtime in the year (marked inactive) | Share of limit used, highest first |
| Monthly comparison | Every driver with a duty in the month | Overtime, highest first |
| Coverage by line | Every line with a trip in the month | Uncovered plus cancelled, highest first |

A month can be chosen from January two years back up to the current month. A month with no published day shows the first section only and a "no published days" message. On a phone the tables collapse to cards.

## Definitions

- **Month.** Service dates in the organization's timezone, 1st to last day. An overnight trip counts on its service day.
- **As-of date.** The end of the chosen month, or today for the current month.
- **Line.** The two end stations of the trip's route, in either order: Αθήνα → Πάτρα and Πάτρα → Αθήνα are one line. Opening a line splits its days by direction. A trip without a route, or whose route has an end station that no longer exists, is grouped as "No line".
- **Trip states.** *Cancelled*: the trip is cancelled. *Uncovered*: no resource assigned and not cancelled. *Covered*: everything else. *Scheduled* = covered + uncovered + cancelled.
- **Coverage rate.** Covered ÷ (covered + uncovered). Cancelled trips are shown separately and are not in the rate.
- **Hours.** Decimal hours (12.5), one decimal place.

### Overtime against the yearly limit

| Column | Meaning |
|---|---|
| Used | The driver's adoption baseline overtime, if the baseline is dated this year, plus non-emergency overtime on published days from 1 January to the as-of date. Days on or before the baseline date are not counted twice. |
| Planned | Non-emergency overtime on published days after the as-of date, up to the end of the chosen month. For a past month it is 0. |
| Limit | The company `overtime_year` value (legal 120 h unless set stricter). |
| Remaining | Limit − used − planned, never below 0. |
| Emergency | Overtime of emergency duties in the year up to the end of the chosen month. It does not count toward the limit. |
| Absolute total | Used + planned + emergency, to compare with `overtime_year_absolute` (180 h). |
| Status | Share = (used + planned) ÷ limit. With a limit of 0, any overtime counts as *Reached*. *Within limits* below 80 %, *Close* from 80 %, *Reached* from 100 %. Shown as text, not only colour. |
| History | *Complete*, or "History unknown before ‹date›". |
| Projection | The month in which the limit is reached at this year's pace. Empty if it is not reached this year, or already reached. |

- **Projection.** Pace = overtime earned from published days this year ÷ days elapsed. The pre-adoption baseline balance is in *Used* but not in the pace. Days are counted from the latest of 1 January, the date history is known from, and the day after the baseline date.
- **History unknown.** If the organization's published history starts after 1 January and the driver has no baseline dated this year or last year, the totals are not complete. The screen shows *Used* and *Absolute total* as "at least ‹n›" and *Remaining* as "at most ‹n›". Unknown history is never shown as 0.

### Monthly comparison

| Column | Meaning |
|---|---|
| Overtime | All overtime in the month, emergency duties included. |
| Work | Total planned work in the month. |
| Days | Service days with a duty. |
| Year average | Average monthly overtime (emergency included) over the earlier, completed months of this year that have at least one published day. Months without a publication are skipped, never counted as 0. Empty if there is no such month. |

The bar beside *Overtime* is relative to the highest row.

### Coverage by line

Uncovered trips are counted by the reason recorded for their day, or "No reason recorded". Opening a line lists each affected day and direction: uncovered trip codes, cancelled trip codes with their own reasons, the day's reason and note, and who published it.

For a day with uncovered trips and no recorded reason, the row also shows «Πλαίσιο, όχι αιτία» / "Context, not a cause": how many drivers were unavailable and how many vehicles were in maintenance or out of service that day, across the whole organization. This is context only; it is not the cause.

## Publish reasons

Publishing a day with at least one uncovered trip (Studio or urgent change) needs a reason. One reason covers the day.

| Value | Label |
|---|---|
| `no_driver` | No driver available |
| `driver_leave` | Driver leave or sickness |
| `no_vehicle` | No vehicle available |
| `work_rules` | Legal working hours limit |
| `other` | Other; a note is required |

The note is optional for the first four, at most 500 characters. Without a reason the publish is refused (`uncovered_reason_required`); `other` without a note is refused (`uncovered_note_required`). On a fully covered day both fields are ignored. The reason and note are stored on the publication and in the scheduling audit entry. Days published before this feature have no reason.

## Exports

Both files are built on the server from the same data as the screen, in the interface language of the user who downloads (Greek or English). File name: `reports-YYYY-MM.xlsx` or `.pdf`.

- **Excel.** Four sheets: Cap, Month, Coverage, About. One bold header row, plain values, no merged cells. The Coverage sheet adds the cancellations and the day notes per line. About holds the organization, month, timezone, generation time, user, the publications used (number of published days from 1 January to the end of the month, and the first 12 characters of the data fingerprint) and the planned-figures statement. All text is written as text, so a note starting with `=`, `+`, `-` or `@` is never run as a formula.
- **PDF.** Landscape A4: title block (organization, month, timezone, generation time, user, published days used, data fingerprint, the statement), the three sections as tables, page numbers. DejaVu Sans is embedded for Greek.
- **Download record.** Each download writes a row in `domain_report_exports`: month, format, user, time and a fingerprint. The screen shows the last export (format, time, user).
- **Changed since last export.** The fingerprint covers the publications in force from 1 January to the end of the month, the delays recorded on those service days (their count and latest record), the company work-rule version and every driver's baseline version. The first 12 characters are printed in each file, so a file can be matched to its download record. If it differs from the last export's, the screen says "The figures changed since the last export on ‹date›". A month is never closed or frozen; download again to get the current figures.

## Known limitations

- Figures are planned, not actual. They are not payroll hours.
- Routes are resolved with today's template data. Moving a template to another route regroups past months under the new line.
- Unknown history is decided for the whole organization (its first publication), not per driver. A driver hired mid-year without a baseline is not flagged separately.
- Past duties use the current route, depot and company-limit data, as in the work rules.
- One reason is recorded per day, not per trip. A day with several different causes needs `other` with a note, or the main cause.
- The context counts for days without a reason are organization-wide, not per line.
- A change of company limits or of any driver baseline marks every exported month of that organization as changed.
- The production image needs `reportlab` (pinned in `backend/uv.lock`) and the DejaVu fonts bundled in `backend/app/domain/reports/fonts/`. Without the fonts the API does not start.

## Deployment

1. Apply migration `0021_management_reports` (`uv run python -m db.migrations upgrade`): the reason columns on `domain_publications` and the `domain_report_exports` table.
2. Refresh the runtime role grants: `uv run python -m db.provision_runtime --refresh-grants`. Without it the Reports screen and every export fail, because the API role cannot read or write the download records.
3. Rebuild the backend image so it contains `reportlab` and the fonts.

`scripts/deploy.sh` does all three: it builds the images, runs the migrations and refreshes the grants.
