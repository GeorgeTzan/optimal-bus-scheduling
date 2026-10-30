"""Real spreadsheet containers and literal values; no parser/business mocks."""

import csv
import io
import zipfile
from dataclasses import replace
from datetime import date, time
import pytest
from app.domain.imports.contracts import ImportLimits, ImportRejected, ReferenceCatalog
from app.domain.imports.templates import generate_template
from app.domain.imports.parsers import parse_upload
from app.domain.imports.references import validate_references


def edited_template(entity, values, locale="en"):
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(generate_template(entity, locale)))
    sheet = next(
        sheet for sheet in book if sheet.title not in ("Instructions", "Οδηγίες")
    )
    sheet.append(values)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_empty_templates_have_no_sample_operational_rows_and_are_versioned():
    from openpyxl import load_workbook

    for entity in (
        "drivers",
        "vehicles",
        "stations",
        "timetable",
        "pairings",
        "transfers",
        "all",
    ):
        for locale in ("en", "el"):
            content = generate_template(entity, locale)
            parsed = parse_upload(content, "template.xlsx", entity, locale)
            assert parsed.schema_version == "ktel-import-v1"
            assert parsed.rows == () and parsed.issues == ()
            workbook = load_workbook(io.BytesIO(content), read_only=True)
            assert workbook.worksheets[0].cell(2, 2).value == "ktel-import-v1"
            assert all(sheet.max_row == 1 for sheet in workbook.worksheets[1:])
            workbook.close()


def test_greek_names_and_leading_zero_references_survive_xlsx_and_csv():
    values = {
        "code": "00107",
        "first_name": "Νίκος",
        "last_name": "Δήμου",
        "phone": "+30 210 1234567",
    }
    for fmt in ("xlsx", "csv"):
        content = generate_template("drivers", "el", [values], file_format=fmt)
        parsed = parse_upload(content, "drivers." + fmt, "drivers", "el")
        assert parsed.issues == ()
        assert len(parsed.rows) == 1
        row = parsed.rows[0]
        assert row.row == 2 and row.entity == "drivers"
        assert row.values["code"] == "00107"
        assert (
            row.values["first_name"] == "Νίκος"
            and row.values["phone"] == "+30 210 1234567"
        )


def test_unknown_headers_and_missing_required_fields_have_cell_positions():
    content = edited_template("drivers", ["00001", "", "Δήμου"])
    parsed = parse_upload(content, "drivers.xlsx", "drivers", "en")
    issue = next(issue for issue in parsed.issues if issue.code == "required")
    assert issue.sheet == "Drivers" and issue.row == 2 and issue.field == "first_name"
    assert issue.column == "First name" and issue.cell == "B2"
    assert "first name" in issue.message.lower()


@pytest.mark.parametrize(
    "filename,content,code",
    [
        ("drivers.dat", b"[ListOfDrom]", "unsupported_format"),
        ("drivers.csv", b"\xff\xfe\x00\x00", "invalid_encoding"),
        ("drivers.xlsx", b"not a ZIP workbook", "invalid_container"),
        ("drivers.csv", b"PK\x03\x04binary", "invalid_content"),
    ],
)
def test_invalid_files_are_rejected_without_lossy_decoding(filename, content, code):
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, filename, "drivers", "en")
    assert error.value.code == code


def test_formulas_are_not_evaluated_or_accepted_as_cached_values():
    content = edited_template("drivers", ["00001", "=1+1", "Δήμου"])
    parsed = parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert any(
        issue.code == "formula" and issue.cell == "B2" for issue in parsed.issues
    )
    assert not parsed.rows[0].is_valid
    csv_content = b'Staff reference,First name,Last name,Phone,Licence number,Home station,Active\n001,=HYPERLINK("https://example.org"),Smith,,,,\n'
    parsed = parse_upload(csv_content, "drivers.csv", "drivers", "en")
    assert any(issue.code == "formula" for issue in parsed.issues)


def altered_archive(content, extra):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as old,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as new,
    ):
        for name in old.namelist():
            new.writestr(name, old.read(name))
        for name, value in extra.items():
            new.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize(
    "member,value,code",
    [
        ("xl/vbaProject.bin", b"not executable", "active_content"),
        ("xl/externalLinks/externalLink1.xml", b"<externalLink/>", "external_link"),
        ("../escape.xml", b"<root/>", "unsafe_container"),
        (
            "xl/worksheets/_rels/sheet1.xml.rels",
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="x" Type="hyperlink" Target="https://example.org" TargetMode="External"/></Relationships>',
            "external_link",
        ),
        (
            "custom.xml",
            b'<!DOCTYPE x [<!ENTITY a "expanded">]><x>&a;</x>',
            "unsafe_xml",
        ),
    ],
)
def test_macros_external_relationships_paths_and_entities_are_blocked(
    member, value, code
):
    content = altered_archive(generate_template("drivers", "en"), {member: value})
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert error.value.code == code


def test_upload_expansion_row_cell_and_text_limits_are_enforced():
    content = generate_template("drivers", "en")
    with pytest.raises(ImportRejected) as error:
        parse_upload(
            content,
            "drivers.xlsx",
            "drivers",
            "en",
            limits=replace(ImportLimits(), max_upload_bytes=10),
        )
    assert error.value.code == "upload_limit"
    bomb = altered_archive(content, {"oversized.xml": b"X" * 500000})
    with pytest.raises(ImportRejected) as error:
        parse_upload(
            bomb,
            "drivers.xlsx",
            "drivers",
            "en",
            limits=replace(ImportLimits(), max_expanded_bytes=100000),
        )
    assert error.value.code == "expanded_limit"
    content = generate_template(
        "drivers",
        "en",
        [
            {"first_name": "One", "last_name": "Driver"},
            {"first_name": "Two", "last_name": "Driver"},
        ],
    )
    with pytest.raises(ImportRejected) as error:
        parse_upload(
            content,
            "drivers.xlsx",
            "drivers",
            "en",
            limits=replace(ImportLimits(), max_rows=1),
        )
    assert error.value.code == "row_limit"
    with pytest.raises(ImportRejected) as error:
        parse_upload(
            content,
            "drivers.xlsx",
            "drivers",
            "en",
            limits=replace(ImportLimits(), max_cells=2),
        )
    assert error.value.code == "cell_limit"
    content = generate_template(
        "drivers", "en", [{"first_name": "A" * 513, "last_name": "Driver"}]
    )
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert error.value.code == "text_limit"


def test_ambiguous_dates_and_non_literal_clocks_require_correction():
    values = {
        "trip_code": "001",
        "origin": "Corinth",
        "destination": "Athens",
        "departure_time": "08:00",
        "arrival_time": "09:30",
        "arrival_day_offset": 0,
        "operating_weekdays": [0, 1, 2, 3, 4],
        "valid_from": "01/02/2026",
        "valid_until": "2026-12-31",
        "allowed_bus_types": ["02"],
    }
    content = generate_template("timetable", "en", [values])
    parsed = parse_upload(content, "timetable.xlsx", "timetable", "en")
    assert any(
        issue.code == "ambiguous_date" and issue.field == "valid_from"
        for issue in parsed.issues
    )
    values.update(valid_from=date(2026, 1, 1), departure_time="0830")
    parsed = parse_upload(
        generate_template("timetable", "en", [values]),
        "timetable.xlsx",
        "timetable",
        "en",
    )
    assert any(issue.code == "invalid_time" for issue in parsed.issues)
    values.update(departure_time=time(8, 0))
    parsed = parse_upload(
        generate_template("timetable", "el", [values]),
        "timetable.xlsx",
        "timetable",
        "el",
    )
    assert not parsed.issues
    assert parsed.rows[0].values["allowed_bus_types"] == ["02"]
    assert parsed.rows[0].values["valid_from"] == "2026-01-01"


def test_numeric_identifiers_cannot_silently_lose_leading_zeroes():
    parsed = parse_upload(
        edited_template("drivers", [107, "Νίκος", "Δήμου"]),
        "drivers.xlsx",
        "drivers",
        "en",
    )
    assert any(
        issue.code == "text_reference_required" and issue.field == "code"
        for issue in parsed.issues
    )


def test_exported_formulas_are_literal_xlsx_and_escaped_csv_text():
    from openpyxl import load_workbook

    values = {"code": "001", "first_name": "=1+1", "last_name": "@someone"}
    content = generate_template("drivers", "en", [values])
    book = load_workbook(io.BytesIO(content), data_only=False)
    assert (
        book["Drivers"]["B2"].data_type == "s" and book["Drivers"]["B2"].value == "=1+1"
    )
    content = generate_template("drivers", "en", [values], file_format="csv")
    row = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))[1]
    assert row[1] == "'=1+1" and row[2] == "'@someone"


def test_pairing_reference_validation_uses_explicit_known_records():
    values = {
        "service_date": "2026-06-01",
        "driver_ref": "001",
        "vehicle_ref": "MISSING",
        "home_station": "BASE",
    }
    workbook = parse_upload(
        generate_template("pairings", "en", [values]), "pairings.xlsx", "pairings", "en"
    )
    issues = validate_references(
        workbook,
        ReferenceCatalog(
            driver_refs=frozenset({"001"}),
            vehicle_refs=frozenset({"BUS001"}),
            station_refs=frozenset({"BASE"}),
        ),
    )
    assert (
        len(issues) == 1
        and issues[0].code == "unknown_reference"
        and issues[0].field == "vehicle_ref"
    )


def replaced_member(content, name, transform):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as old,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as new,
    ):
        for key in old.namelist():
            new.writestr(
                key, transform(old.read(key)) if key == name else old.read(key)
            )
    return output.getvalue()


def test_malformed_row_coordinates_return_a_safe_file_error():
    content = generate_template(
        "drivers", "en", [{"first_name": "Nikos", "last_name": "Dimou"}]
    )
    content = replaced_member(
        content,
        "xl/worksheets/sheet2.xml",
        lambda data: data.replace(b'<row r="2">', b'<row r="invalid">'),
    )
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert error.value.code == "invalid_container"


def test_individual_style_components_cannot_bypass_the_style_budget():
    from xml.etree import ElementTree as XML

    def excess_fonts(data):
        root = XML.fromstring(data)
        fonts = root.find("{*}fonts")
        for _ in range(130):
            fonts.append(
                XML.Element(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}font"
                )
            )
        fonts.set("count", str(len(fonts)))
        return XML.tostring(root)

    content = replaced_member(
        generate_template("drivers", "en"), "xl/styles.xml", excess_fonts
    )
    with pytest.raises(ImportRejected) as error:
        parse_upload(
            content,
            "drivers.xlsx",
            "drivers",
            "en",
            limits=replace(ImportLimits(), max_styles=128),
        )
    assert error.value.code == "style_limit"


def test_a_false_small_dimension_cannot_hide_actual_data_rows():
    content = generate_template(
        "drivers", "en", [{"code": "001", "first_name": "Nikos", "last_name": "Dimou"}]
    )
    content = replaced_member(
        content,
        "xl/worksheets/sheet2.xml",
        lambda data: data.replace(
            b'<dimension ref="A1:G2"/>', b'<dimension ref="A1:A1"/>'
        ),
    )
    result = parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert len(result.rows) == 1 and result.rows[0].values["code"] == "001"


@pytest.mark.parametrize("locale,sheet", [("en", "Drivers"), ("el", "Οδηγοί")])
def test_generated_workbook_is_readable_by_independent_calamine_engine(
    tmp_path, locale, sheet
):
    from python_calamine import CalamineWorkbook

    file = tmp_path / "actual-template.xlsx"
    file.write_bytes(
        generate_template(
            "drivers",
            locale,
            [{"code": "00001", "first_name": "=1+1", "last_name": "Δήμου"}],
        )
    )
    book = CalamineWorkbook.from_path(str(file))
    rows = book.get_sheet_by_name(sheet).to_python()
    assert rows[1][0:3] == ["00001", "=1+1", "Δήμου"]
    book.close()


def test_empty_formatted_columns_are_harmless_but_unheaded_values_are_not_dropped():
    from openpyxl import load_workbook

    content = generate_template(
        "drivers", "en", [{"code": "001", "first_name": "Nikos", "last_name": "Dimou"}]
    )
    book = load_workbook(io.BytesIO(content))
    book["Drivers"]["H1"].number_format = "@"
    output = io.BytesIO()
    book.save(output)
    assert not parse_upload(output.getvalue(), "drivers.xlsx", "drivers", "en").issues
    book["Drivers"]["H2"] = "Keep this source value"
    output = io.BytesIO()
    book.save(output)
    result = parse_upload(output.getvalue(), "drivers.xlsx", "drivers", "en")
    assert any(
        issue.code == "unknown_column" and issue.cell == "H2" for issue in result.issues
    )
    assert (
        result.rows[0].raw["_unmapped_columns"][0]["value"] == "Keep this source value"
    )


def test_full_workbook_keeps_all_nonempty_sheets_in_one_parse_result():
    content = generate_template(
        "all",
        "en",
        {
            "drivers": [{"code": "001", "first_name": "Nikos", "last_name": "Dimou"}],
            "vehicles": [
                {"code": "BUS001", "registration_plate": "kra-1234", "bus_type": "02"}
            ],
        },
    )
    result = parse_upload(content, "complete.xlsx", "drivers", "en")
    assert not result.issues and [row.entity for row in result.rows] == [
        "drivers",
        "vehicles",
    ]
    assert result.rows[1].values["registration_plate"] == "KRA-1234"


def test_bounded_error_details_never_turn_later_invalid_rows_into_valid_rows():
    content = generate_template(
        "drivers",
        "en",
        [{"code": f"{n:05d}", "last_name": "Driver"} for n in range(10)],
    )
    result = parse_upload(
        content,
        "drivers.xlsx",
        "drivers",
        "en",
        limits=replace(ImportLimits(), max_issues=3),
    )
    assert len(result.rows) == 10 and len(result.issues) == 3 and not result.is_valid
    assert all(not row.is_valid for row in result.rows)
    assert result.issues[-1].code == "more_errors"


@pytest.mark.parametrize("fmt", ["xlsx", "csv"])
def test_template_language_survives_ui_language_changes(fmt):
    values = {
        "trip_code": "001",
        "origin": "Αφετηρία",
        "destination": "Προορισμός",
        "departure_time": "08:00",
        "arrival_time": "09:00",
        "arrival_day_offset": 0,
        "operating_weekdays": [0],
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "allowed_bus_types": ["02"],
        "distance_km": "1,5",
    }
    result = parse_upload(
        generate_template("timetable", "el", [values], file_format=fmt),
        "timetable." + fmt,
        "timetable",
        "en",
    )
    assert not result.issues and result.rows[0].values["distance_km"] == 1.5
    assert result.locale == "en" and result.source_locale == "el"
    invalid = parse_upload(
        generate_template("drivers", "el", [{"last_name": "Δήμου"}], file_format=fmt),
        "drivers." + fmt,
        "drivers",
        "en",
    )
    issue = next(issue for issue in invalid.issues if issue.field == "first_name")
    assert (
        issue.column == "Όνομα"
        and issue.cell == "B2"
        and issue.message.startswith("Enter")
    )


def test_csv_safety_escape_does_not_change_literal_apostrophe_references():
    source = {"code": "'=001", "first_name": "'@Νίκος", "last_name": "Δήμου"}
    result = parse_upload(
        generate_template("drivers", "en", [source], file_format="csv"),
        "drivers.csv",
        "drivers",
        "en",
    )
    assert not result.issues
    assert result.rows[0].values["code"] == source["code"]
    assert result.rows[0].values["first_name"] == source["first_name"]


def test_template_guidance_and_dropdowns_use_the_active_upload_limits():
    from openpyxl import load_workbook

    content = generate_template(
        "drivers",
        "en",
        limits=replace(ImportLimits(), max_rows=17, max_upload_bytes=1024 * 1024),
    )
    book = load_workbook(io.BytesIO(content))
    instructions = " ".join(
        str(cell.value) for row in book["Instructions"] for cell in row if cell.value
    )
    assert "17" in instructions and "1 MB" in instructions
    assert any(
        str(rule.sqref) == "G2:G18"
        for rule in book["Drivers"].data_validations.dataValidation
    )


@pytest.mark.parametrize("locale", ["en", "el"])
def test_complete_workbook_types_are_readable_independently(tmp_path, locale):
    from python_calamine import CalamineWorkbook
    from app.domain.imports.template_schema import title

    source = {
        "drivers": [{"code": "00001", "first_name": "Νίκος", "last_name": "Δήμου"}],
        "vehicles": [
            {
                "code": "BUS001",
                "registration_plate": "KRA-1234",
                "bus_type": "02",
                "capacity": 42,
            }
        ],
        "timetable": [
            {
                "trip_code": "T001",
                "origin": "Αφετηρία",
                "destination": "Προορισμός",
                "departure_time": "08:00",
                "arrival_time": "09:30",
                "arrival_day_offset": 0,
                "operating_weekdays": [0],
                "valid_from": "2026-01-01",
                "valid_until": "2026-12-31",
                "allowed_bus_types": ["02"],
                "distance_km": 1.5,
            }
        ],
    }
    file = tmp_path / "complete.xlsx"
    file.write_bytes(generate_template("all", locale, source))
    book = CalamineWorkbook.from_path(str(file))
    assert len(book.sheet_names) == 8
    vehicle = book.get_sheet_by_name(title("vehicles", locale)).to_python()[1]
    trip = book.get_sheet_by_name(title("timetable", locale)).to_python()[1]
    assert vehicle[0] == "BUS001" and vehicle[2] == "02" and vehicle[3] == 42
    assert (
        trip[0] == "T001"
        and trip[3] == "08:00"
        and trip[7] == "2026-01-01"
        and trip[9] == "02"
        and trip[10] == 1.5
    )
    book.close()


@pytest.mark.parametrize("unmapped", [False, True])
def test_invalid_native_numbers_keep_json_safe_provenance_and_cell_types(unmapped):
    import json
    from dataclasses import asdict
    from xml.etree import ElementTree as XML

    content = generate_template(
        "stations", "en", [{"name_el": "Base", "latitude": 1.5}]
    )

    def overflow(data):
        root = XML.fromstring(data)
        cell = root.find('.//{*}c[@r="E2"]')
        cell.find("{*}v").text = "1e999"
        if unmapped:
            cell.set("r", "H2")
            row = root.find('.//{*}row[@r="2"]')
            row.remove(cell)
            row.append(cell)
        return XML.tostring(root)

    result = parse_upload(
        replaced_member(content, "xl/worksheets/sheet2.xml", overflow),
        "stations.xlsx",
        "stations",
        "en",
    )
    assert not result.is_valid
    json.dumps(asdict(result), allow_nan=False)
    if unmapped:
        assert result.rows[0].raw["_unmapped_columns"][0]["data_type"] == "n"
    else:
        assert result.rows[0].cell_types["latitude"] == "n"


def test_decimal_overflow_is_a_correctable_cell_error_not_a_json_infinity():
    import json
    from dataclasses import asdict

    source = {"name_el": "Base", "latitude": "9" * 400}
    result = parse_upload(
        generate_template("stations", "en", [source]), "stations.xlsx", "stations", "en"
    )
    assert any(
        issue.code == "invalid_number" and issue.field == "latitude"
        for issue in result.issues
    )
    json.dumps(asdict(result), allow_nan=False)


def test_unordered_cell_addresses_cannot_hide_unheaded_source_values():
    content = generate_template(
        "stations", "en", [{"name_el": "Base", "latitude": 1.5}]
    )
    content = replaced_member(
        content,
        "xl/worksheets/sheet2.xml",
        lambda data: data.replace(b'r="E2"', b'r="H2"'),
    )
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, "stations.xlsx", "stations", "en")
    assert error.value.code == "invalid_container"


def test_unrecognized_value_namespace_cannot_silently_erase_optional_fields():
    from xml.etree import ElementTree as XML

    content = generate_template(
        "drivers",
        "en",
        [{"first_name": "Nikos", "last_name": "Dimou", "phone": "+302101234567"}],
    )

    def wrong_namespace(data):
        root = XML.fromstring(data)
        text = root.find('.//{*}c[@r="D2"]/{*}is/{*}t')
        text.tag = "{urn:unsupported-value}t"
        return XML.tostring(root)

    content = replaced_member(content, "xl/worksheets/sheet2.xml", wrong_namespace)
    with pytest.raises(ImportRejected) as error:
        parse_upload(content, "drivers.xlsx", "drivers", "en")
    assert error.value.code == "invalid_container"


def test_travel_note_validation_matches_the_canonical_manual_entry_contract():
    result=parse_upload(generate_template('transfers','en',[{'origin':'001','destination':'002','minutes':30,'source_note':'x'*301}]),'travel.xlsx','transfers','en')
    assert not result.is_valid
    assert any(issue.field=='source_note' and issue.cell=='D2' for issue in result.issues)
