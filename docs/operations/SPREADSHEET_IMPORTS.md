# Supported spreadsheet contract

Task 6 provides tested template generation and pure parsing. The durable upload/review/commit API and guided import screen follow in Tasks 7–8. Parsing does not write operational records, confirm pairings or publish schedules. The older DAT/JSON fixture helpers are not supported customer upload formats.

Templates use `ktel-import-v1`. Download the relevant Drivers, Vehicles or Timetable template by default; the complete workbook also includes optional Stations, Pairings, Connections and Travel times. Examples occur only in Instructions. Operational sheets contain headings without example records. Optional Connections use incoming/following trip references. They require the same vehicle on dates when both trips operate; branching and cyclic links are rejected. Preview validates the complete proposed graph, including new timetable rows in the same workbook. Travel durations are a separate concept. Required spreadsheet headings are teal; optional headings are navy, with a legend in Instructions.

References are text. Preserve values such as `00001`; numeric Excel references are rejected because missing leading zeroes cannot be recovered reliably. Format reference cells as Text **before** typing. Merely changing the format of an already numeric value does not recover lost digits. New drivers may omit staff references; the forthcoming persisted preview must allocate stable references and return a populated workbook. Matching people by name alone is not a parser operation.

Drivers require first/last names. Vehicles require a registration or stable vehicle reference plus their actual fleet category. Unknown capacity is blank. Timetables require a stable trip reference, origin/destination, local clocks, an explicit arrival day, weekdays, validity dates and actual eligible vehicle categories. Station references/names are resolved against tenant records and the entire reviewed batch; a parsed string is not proof of a valid relationship. Imported pairings still require explicit service-day confirmation.

Use ISO dates (`2026-06-01`) and minute clocks (`08:30`). Native Excel date/time values are accepted without rounding seconds or selecting a timezone/DST occurrence. Ambiguous slash dates such as `01/02/2026` require correction. Weekdays use the localized template abbreviations (`Mon Tue Wed`, `Δευ Τρι Τετ`); multiple eligible categories use `02 | 03`. Arrival day is an explicit dropdown, never inferred from the clocks. Yes/No and Ναι/Όχι are supported boolean values.

XLSX declares its source language in versioned Instructions. UTF-8 CSV uses the exact supplied localized headers and delimiter (English comma; Greek semicolon). Those explicit source contracts govern decimal/layout parsing even after a UI language toggle. Error messages use the UI language, while sheet/column labels and cell addresses identify the actual source file. Unsupported or ambiguous layouts are rejected instead of guessed. CSV BOM is optional.

Exports write formula-looking XLSX values as literal text. CSV escapes spreadsheet operators and leading apostrophes reversibly. Operational formulas are rejected with “paste values” guidance; no formulas are evaluated. Macros, embedded binary objects, external relationships, unsafe ZIP paths, encrypted archives and XML entities are blocked before the workbook reader builds objects. The package guard also bounds XML depth/nodes, styles and individual style-component collections. File/container failures are safe errors, not raw library tracebacks. Repeated/out-of-order cell/row addresses and unrecognized core value namespaces are rejected before the reader can skip data. Nonfinite/oversized native numbers remain JSON-safe source literals with their original cell types; invalid values cannot become valid merely because a preview is serialized.

Empty sheets and empty formatted columns do not create records or errors. Unexpected nonempty cells block saving and remain in row provenance; they are not silently dropped. Duplicate references are flagged. Issues carry stable code, sheet, row, actual column label, field key and cell address. Detailed messages are capped, while later invalid rows remain invalid. The forthcoming commit layer must enforce both workbook and row errors atomically.

## Default bounded capacity

`ImportLimits` is supplied to parser/template generation by the caller; templates show the same active row/upload limit. The customer API will expose its effective limits before upload. The current defaults are:

| Boundary | Default |
|---|---:|
| Uploaded bytes | 5 MiB |
| Expanded ZIP bytes | 25 MiB |
| ZIP members / workbook sheets | 128 / 8 |
| Nonempty operational rows, across the workbook | 5,000 |
| Columns / actual cells | 32 / 100,000 |
| Text characters per cell | 512 |
| XF styles and each style-component collection | 1,024 |
| Detailed issues | 200 |
| XML depth | 32 |

Very sparse, distant row addresses are also rejected to bound iteration. Split larger files into supported batches; do not increase limits or advertise unlimited imports without new measurements.

Local synthetic measurement, 2026-10-31: 5,000 recurring services with 160-character Greek origin and destination names. XLSX: 266,575 uploaded bytes, 6,770,439 expanded bytes; generation 2.212s, parsing 4.606s. CSV: 3,725,351 bytes; generation 0.141s, parsing 1.152s. Whole-process peak RSS (including template generation) was 96.6 MiB / 92.8 MiB respectively. These measure parser/export behavior; database commit throughput, concurrent uploads and overall SaaS capacity remain separate acceptance gates.

Reproduce with `cd backend && uv run python -m tests.performance.benchmark_imports --entity timetable --format xlsx --rows 5000 --long-text` (or `--format csv`). The 5,000-row export regression uses a generous 10s limit; it first reproduced a 21.09s quadratic scan, then passed after direct cell access replaced repeated worksheet scans.

## Implementation and interoperability

`app/domain/imports/templates.py` generates workbooks/CSV. `parsers.py` coordinates parsing, `xlsx_safety.py` preflights containers and `cell_values.py` normalizes literals. Resource/calendar validation reuses canonical contracts. `references.py` accepts an explicit tenant-derived catalog; database-backed resolution and revalidation are part of Task 7.

Production dependencies: [openpyxl 3.1.5](https://pypi.org/project/openpyxl/) and defusedxml. The publisher documents the XML-entity requirement; our guards add independent byte/shape/content limits. [The reader API](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html) is used in read-only mode with formula values retained for rejection and external-link retention disabled. Independent generated-workbook tests use [python-calamine](https://github.com/dimastbk/python-calamine) as a development-only reader, covering English/Greek names, leading zeroes, literal formula-looking values, categories, dates, clocks and numeric values. This is interoperability evidence, not a claim that a dependency has no vulnerabilities.

Durable review and retention (Task 7)
-----------------------------------
Uploads are tenant-owned PostgreSQL batches and rows. Preview writes no operational records. Corrections, refresh and save require the current batch version; saving checks the canonical source snapshot and applies all nonempty sheets in one transaction. Missing person references in a populated register need an explicit new/existing choice. Every sheet requires its normal manual-entry write capability. Exact source retries and committed save retries reuse the saved result.

Completed workbooks contain commit-time values with assigned human references; omitted optional values retain their saved value. Later manual edits do not rewrite this download. Error CSVs are safe diagnostic reports, not replacement import files. Source copies expire after seven days for pending previews and thirty days after commit (configurable). Expired copies and filenames become inaccessible immediately; committed result summaries and canonical records remain.

Run retention per organization with the restricted API runtime connection:

```sh
cd backend
uv run python -m app.cli.purge_imports --tenant-id 1 --limit 100
```

Each invocation removes at most 100 expired batch payloads in a transaction and appends retention audit events. Schedule this command for each configured tenant; no public purge endpoint or cross-tenant worker access is provided. Physical database backups follow a separate operator retention policy.

Telemetry accepts only event identifiers, severity and exception class/stack location. Request bodies, URLs, cookies, headers, breadcrumbs, SQL exception messages, local variables and performance payloads are excluded before transport. This deliberately limits diagnosis detail to keep staff records and uploaded cells out of external error reporting.

For the durable PostgreSQL probe (separate from routine unit tests), run:

```sh
uv run pytest -s tests/performance/benchmark_durable_imports.py
```

It provisions and drops a disposable database with restricted runtime roles, creates 5000 test drivers through the real upload/save APIs, and downloads their completed workbook. It does not use or alter an existing customer organization.

The live default is **1000 total operational rows per file**, 5MiB upload. The parser/configuration ceiling remains5000 rows. The explicit5000-driver PostgreSQL probe passed (stage11.300s, save49.038s, export2.213s, peak292.9MiB), but is too slow as a normal interactive default. At1000 rows the measured path is stage2.630s/save10.018s/export0.424s, peak214.6MiB. These are local restricted-role measurements, not a concurrent-load benchmark or an external deployment SLA. `IMPORT_MAX_ROWS` may be configured within1..5000 after deployment-specific capacity/timeout validation. Templates and capabilities show the configured limit. Run the default-size probe with `KTEL_IMPORT_PROBE_ROWS=1000`.
