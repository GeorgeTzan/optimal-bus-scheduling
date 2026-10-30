"""Preflight ZIP/XML bytes before the spreadsheet library creates workbook objects."""

import io
import zipfile
from pathlib import PurePosixPath
from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException
from openpyxl.utils.cell import coordinate_to_tuple
from app.domain.imports.contracts import reject_import as reject


def inspect_package(content, limits, locale):
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, ValueError):
        reject(
            "invalid_container",
            "This is not a readable XLSX workbook.",
            "Το αρχείο δεν είναι αναγνώσιμο βιβλίο XLSX.",
            locale,
        )
    try:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(members) > limits.max_members or len(set(names)) != len(names):
            reject(
                "unsafe_container",
                "The workbook has too many or repeated internal files.",
                "Το βιβλίο έχει υπερβολικά ή επαναλαμβανόμενα εσωτερικά αρχεία.",
                locale,
            )
        if sum(member.file_size for member in members) > limits.max_expanded_bytes:
            reject(
                "expanded_limit",
                "The expanded workbook is too large. Split it into smaller files.",
                "Το αποσυμπιεσμένο βιβλίο είναι πολύ μεγάλο. Χωρίστε το σε μικρότερα αρχεία.",
                locale,
            )
        cells = styles = strings = nodes = 0
        style_components = {}
        for member in members:
            name = member.filename
            lower = name.casefold()
            if (
                "\\" in name
                or "\x00" in name
                or PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or member.flag_bits & 1
            ):
                reject(
                    "unsafe_container",
                    "Use an ordinary, unencrypted XLSX workbook.",
                    "Χρησιμοποιήστε ένα κανονικό βιβλίο XLSX χωρίς κρυπτογράφηση.",
                    locale,
                )
            if lower.endswith(".bin") or any(
                part in lower for part in ("vbaproject", "activex", "embeddings/")
            ):
                reject(
                    "active_content",
                    "Remove macros and embedded objects before uploading.",
                    "Αφαιρέστε μακροεντολές και ενσωματωμένα αντικείμενα.",
                    locale,
                )
            if "externallink" in lower:
                reject(
                    "external_link",
                    "Remove external links before uploading.",
                    "Αφαιρέστε τους εξωτερικούς συνδέσμους πριν την εισαγωγή.",
                    locale,
                )
            if member.file_size > max(1, member.compress_size) * 1000:
                reject(
                    "expanded_limit",
                    "This workbook expands too much. Save a smaller values-only workbook.",
                    "Το βιβλίο αποσυμπιέζεται υπερβολικά. Αποθηκεύστε μικρότερο αρχείο μόνο με τιμές.",
                    locale,
                )
            if not lower.endswith((".xml", ".rels")):
                reject(
                    "unsupported_content",
                    "Use the supplied workbook without embedded attachments.",
                    "Χρησιμοποιήστε το παρεχόμενο πρότυπο χωρίς ενσωματωμένα συνημμένα.",
                    locale,
                )
            depth = 0
            worksheet = lower.startswith("xl/worksheets/") and lower.endswith(".xml")
            current_row = None
            last_row = 0
            last_column = 0
            try:
                with archive.open(member) as source:
                    for event, node in SafeXML.iterparse(
                        source,
                        events=("start", "end"),
                        forbid_dtd=True,
                        forbid_entities=True,
                        forbid_external=True,
                    ):
                        tag = node.tag.rsplit("}", 1)[-1]
                        if event == "start":
                            depth += 1
                            nodes += 1
                            if depth > 32 or nodes > limits.max_cells * 16 + 10000:
                                reject(
                                    "unsafe_xml",
                                    "The workbook structure is too complex. Paste values into a fresh template.",
                                    "Η δομή του βιβλίου είναι υπερβολικά σύνθετη. Επικολλήστε τιμές σε νέο πρότυπο.",
                                    locale,
                                )
                            if (
                                node.attrib.get("TargetMode", "").casefold()
                                == "external"
                            ):
                                reject(
                                    "external_link",
                                    "Remove external links before uploading.",
                                    "Αφαιρέστε τους εξωτερικούς συνδέσμους πριν την εισαγωγή.",
                                    locale,
                                )
                            if lower == "[content_types].xml" and any(
                                word in node.attrib.get("ContentType", "").casefold()
                                for word in (
                                    "macroenabled",
                                    "vba",
                                    "activex",
                                    "oleobject",
                                )
                            ):
                                reject(
                                    "active_content",
                                    "Remove macros and embedded objects before uploading.",
                                    "Αφαιρέστε μακροεντολές και ενσωματωμένα αντικείμενα.",
                                    locale,
                                )
                            if (
                                worksheet
                                and (
                                    tag in ("worksheet", "sheetData", "row", "c")
                                    or current_row is not None
                                    and tag in ("v", "f", "is", "t", "r")
                                )
                                and node.tag
                                != "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                                + tag
                            ):
                                reject(
                                    "invalid_container",
                                    "A worksheet value uses an unsupported format. Paste values into a fresh template.",
                                    "Μια τιμή φύλλου χρησιμοποιεί μη υποστηριζόμενη μορφή. Επικολλήστε τιμές σε νέο πρότυπο.",
                                    locale,
                                )
                            if tag == "c":
                                cells += 1
                                if cells > limits.max_cells:
                                    reject(
                                        "cell_limit",
                                        "There are too many cells. Split the file.",
                                        "Υπάρχουν υπερβολικά πολλά κελιά. Χωρίστε το αρχείο.",
                                        locale,
                                    )
                                try:
                                    r, c = coordinate_to_tuple(node.attrib["r"])
                                except (ValueError, KeyError):
                                    reject(
                                        "invalid_container",
                                        "A cell address is invalid. Save a fresh XLSX copy.",
                                        "Μια διεύθυνση κελιού δεν είναι έγκυρη. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                        locale,
                                    )
                                if r < 1 or c < 1:
                                    reject(
                                        "invalid_container",
                                        "A cell address is invalid. Save a fresh XLSX copy.",
                                        "Μια διεύθυνση κελιού δεν είναι έγκυρη. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                        locale,
                                    )
                                if worksheet:
                                    if r != current_row or c <= last_column:
                                        reject(
                                            "invalid_container",
                                            "Cell addresses are repeated or out of order. Save a fresh XLSX copy.",
                                            "Οι διευθύνσεις κελιών επαναλαμβάνονται ή δεν έχουν σωστή σειρά. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                            locale,
                                        )
                                    last_column = c
                                if c > limits.max_columns or r > limits.max_rows + 128:
                                    reject(
                                        "row_limit",
                                        "Remove unused rows/columns or split the file.",
                                        "Αφαιρέστε αχρησιμοποίητες γραμμές/στήλες ή χωρίστε το αρχείο.",
                                        locale,
                                    )
                            if tag == "row":
                                try:
                                    row_number = int(
                                        node.attrib.get("r", str(last_row + 1))
                                    )
                                except ValueError:
                                    reject(
                                        "invalid_container",
                                        "A row address is invalid. Save a fresh XLSX copy.",
                                        "Μια διεύθυνση γραμμής δεν είναι έγκυρη. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                        locale,
                                    )
                                if row_number < 1:
                                    reject(
                                        "invalid_container",
                                        "A row address is invalid. Save a fresh XLSX copy.",
                                        "Μια διεύθυνση γραμμής δεν είναι έγκυρη. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                        locale,
                                    )
                                if worksheet:
                                    if (
                                        current_row is not None
                                        or row_number <= last_row
                                    ):
                                        reject(
                                            "invalid_container",
                                            "Row addresses are repeated or out of order. Save a fresh XLSX copy.",
                                            "Οι διευθύνσεις γραμμών επαναλαμβάνονται ή δεν έχουν σωστή σειρά. Αποθηκεύστε νέο αντίγραφο XLSX.",
                                            locale,
                                        )
                                    current_row = last_row = row_number
                                    last_column = 0
                                if row_number > limits.max_rows + 128:
                                    reject(
                                        "row_limit",
                                        "Remove unused rows or split the file.",
                                        "Αφαιρέστε αχρησιμοποίητες γραμμές ή χωρίστε το αρχείο.",
                                        locale,
                                    )
                            if lower == "xl/styles.xml" and tag in (
                                "font",
                                "fill",
                                "border",
                                "numFmt",
                                "cellStyle",
                            ):
                                style_components[tag] = style_components.get(tag, 0) + 1
                                if style_components[tag] > limits.max_styles:
                                    reject(
                                        "style_limit",
                                        "There are too many cell styles. Paste values into a fresh template.",
                                        "Υπάρχουν υπερβολικά πολλά στυλ κελιών. Επικολλήστε τιμές σε νέο πρότυπο.",
                                        locale,
                                    )
                            if tag == "xf":
                                styles += 1
                                if styles > limits.max_styles:
                                    reject(
                                        "style_limit",
                                        "There are too many cell styles. Paste values into a fresh template.",
                                        "Υπάρχουν υπερβολικά πολλά στυλ κελιών. Επικολλήστε τιμές σε νέο πρότυπο.",
                                        locale,
                                    )
                            if tag == "si":
                                strings += 1
                                if strings > limits.max_cells:
                                    reject(
                                        "cell_limit",
                                        "There are too many text entries. Split the file.",
                                        "Υπάρχουν υπερβολικά πολλές εγγραφές κειμένου. Χωρίστε το αρχείο.",
                                        locale,
                                    )
                        else:
                            if (
                                node.text
                                and len(node.text) > limits.max_cell_chars
                                and tag in ("t", "v")
                            ):
                                reject(
                                    "text_limit",
                                    "A cell contains too much text. Shorten it before uploading.",
                                    "Ένα κελί περιέχει υπερβολικά μεγάλο κείμενο. Συντομεύστε το πριν την εισαγωγή.",
                                    locale,
                                )
                            if worksheet and tag == "row":
                                current_row = None
                            depth -= 1
                            node.clear()
            except (DefusedXmlException, SafeXML.ParseError):
                reject(
                    "unsafe_xml",
                    "The workbook contains unsafe or invalid XML. Use a fresh template.",
                    "Το βιβλίο περιέχει μη ασφαλή ή μη έγκυρα δεδομένα XML. Χρησιμοποιήστε νέο πρότυπο.",
                    locale,
                )
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
                reject(
                    "invalid_container",
                    "The workbook could not be read. Save a fresh XLSX copy.",
                    "Δεν ήταν δυνατή η ανάγνωση του βιβλίου. Αποθηκεύστε νέο αντίγραφο XLSX.",
                    locale,
                )
    finally:
        archive.close()
