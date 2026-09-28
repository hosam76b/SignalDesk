"""Dependency-free .xlsx workbook writers (single sheet, raw OOXML).

Two entry points share the same OOXML parts:

``build_minimal_xlsx``
    Buffer-everything writer for small, already-materialised result sets.
``StreamingXlsxWriter``
    Incremental writer that pushes rows straight into the ZIP archive, so a
    large export never holds the sheet (let alone the workbook) in memory.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Iterable, Iterator, Sequence

#: Excel refuses to open a cell longer than this, and silently truncating on
#: the way in is the only way to keep a workbook with long post bodies valid.
MAX_CELL_CHARS = 32767

#: Style indices into the ``cellXfs`` list emitted by ``_STYLES_XML`` below.
STYLE_DEFAULT = 0
STYLE_HEADER = 1
STYLE_BODY = 2

_STYLES_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F5F66"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

_CONTENT_TYPES_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''

_ROOT_RELS_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''

_WORKBOOK_RELS_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''

_APP_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Excel</Application></Properties>'''

_CORE_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>SignalDesk</dc:creator><cp:lastModifiedBy>SignalDesk</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:modified></cp:coreProperties>'''


def _excel_col(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _escape_text(value: str) -> str:
    # Control characters are illegal in XML 1.0 even when escaped, so they are
    # dropped rather than encoded: post bodies scraped from the wild regularly
    # carry stray \x00-\x08 bytes that would otherwise corrupt the archive.
    cleaned = "".join(
        char for char in value
        if char in "\t\n\r" or 0x20 <= ord(char) < 0xD800 or 0xE000 <= ord(char) <= 0xFFFD
    )
    return cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate_cell(value: str) -> str:
    if len(value) <= MAX_CELL_CHARS:
        return value
    return value[: MAX_CELL_CHARS - 1] + "…"


def _utf8(text: str) -> bytes:
    """`ZipExtFile.write` takes bytes, and the sheet part is written as UTF-8."""
    return text.encode("utf-8")


def _cell_xml(ref: str, value: Any, style: int) -> str:
    """Render one OOXML cell. `None` yields an empty string (sparse cell)."""
    if value is None:
        return ""
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, bool):
        text = "TRUE" if value else "FALSE"
        return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{text}</t></is></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style_attr} t="n"><v>{value}</v></c>'
    text = _escape_text(_truncate_cell(str(value)))
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _workbook_xml(sheet_name: str) -> str:
    safe_name = _escape_text(sheet_name)[:31] or "Sheet1"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{safe_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )


class StreamingXlsxWriter:
    """Build a single-sheet .xlsx workbook incrementally, straight into a ZIP.

    The sheet part is streamed into the archive with ``ZipFile.open(..., "w")``
    as rows arrive, so peak memory is one ZIP compression block regardless of
    how many rows are written. Use it as a context manager, or call
    :meth:`finalize` followed by :meth:`iter_bytes` and then :meth:`close`.
    """

    def __init__(
        self,
        sheet_name: str = "Sheet1",
        *,
        header: Sequence[str] = (),
        column_widths: Sequence[int] | None = None,
        autofilter: bool = True,
        freeze_header: bool = True,
    ) -> None:
        self._buffer = io.BytesIO()
        # force_zip64 because the final size is unknown while streaming; without
        # it, crossing 2 GiB mid-write raises instead of finalising.
        self._zip = zipfile.ZipFile(self._buffer, "w", zipfile.ZIP_DEFLATED)
        self._column_count = max(len(header), 1)
        self._row_count = 0
        self._sheet_name = sheet_name
        self._autofilter = autofilter
        self._finalized = False
        self._closed = False

        self._zip.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        self._zip.writestr("_rels/.rels", _ROOT_RELS_XML)
        self._zip.writestr("docProps/core.xml", _CORE_XML)
        self._zip.writestr("docProps/app.xml", _APP_XML)
        self._zip.writestr("xl/workbook.xml", _workbook_xml(sheet_name))
        self._zip.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML)
        self._zip.writestr("xl/styles.xml", _STYLES_XML)

        self._sheet = self._zip.open("xl/worksheets/sheet1.xml", "w", force_zip64=True)
        self._sheet.write(_utf8(self._sheet_preamble(header, column_widths, freeze_header)))
        if header:
            self._row_count = 1
            self._sheet.write(_utf8(
                f'<row r="1">'
                + "".join(
                    _cell_xml(f"{_excel_col(col)}1", label, STYLE_HEADER)
                    for col, label in enumerate(header, start=1)
                )
                + "</row>"
            ))

    def _sheet_preamble(
        self,
        header: Sequence[str],
        column_widths: Sequence[int] | None,
        freeze_header: bool,
    ) -> str:
        last_col = _excel_col(self._column_count)
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        ]
        if freeze_header and header:
            parts.append(
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                "</sheetView></sheetViews>"
            )
        parts.append('<sheetFormatPr defaultRowHeight="15"/>')
        if column_widths:
            cols = "".join(
                f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
                for index, width in enumerate(column_widths, start=1)
                if width
            )
            if cols:
                parts.append(f"<cols>{cols}</cols>")
        parts.append(f'<sheetData><dimension ref="A1:{last_col}1"/>')
        return "".join(parts)

    @property
    def rows_written(self) -> int:
        """Data rows written so far, excluding the header row."""
        return max(0, self._row_count - (1 if self._sheet_name and self._row_count else 0))

    def add_row(self, values: Iterable[Any]) -> None:
        """Append one data row. The writer must not be finalized."""
        if self._finalized:
            raise RuntimeError("Cannot add rows after finalize()")
        self._row_count += 1
        row_index = self._row_count
        cells = "".join(
            _cell_xml(f"{_excel_col(col)}{row_index}", value, STYLE_BODY)
            for col, value in enumerate(values, start=1)
        )
        self._sheet.write(_utf8(f'<row r="{row_index}">{cells}</row>'))

    def finalize(self) -> None:
        """Close the sheet part. Must be called before :meth:`iter_bytes`."""
        if self._finalized:
            return
        self._finalized = True
        tail = "</sheetData>"
        if self._autofilter and self._row_count:
            last = f"{_excel_col(self._column_count)}{self._row_count}"
            tail += f'<autoFilter ref="A1:{last}"/>'
        tail += "</worksheet>"
        self._sheet.write(_utf8(tail))
        self._sheet.close()
        self._zip.close()

    def iter_bytes(self, block_size: int = 262144) -> Iterator[bytes]:
        """Yield the finished workbook in blocks instead of one big bytes object."""
        if not self._finalized:
            self.finalize()
        self._buffer.seek(0)
        while True:
            block = self._buffer.read(block_size)
            if not block:
                break
            yield block

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._finalized:
            self.finalize()
        self._buffer.close()

    def __enter__(self) -> "StreamingXlsxWriter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def build_minimal_xlsx(rows: list[list[Any]], sheet_name: str = "Sheet1") -> bytes:
    """Build a minimal single-sheet .xlsx workbook from a list of rows (first row = header)."""
    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cell_xml = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{_excel_col(col_idx)}{row_idx}"
            if isinstance(value, (int, float)):
                cell_xml.append(f'<c r="{ref}" t="n"><v>{value}</v></c>')
            else:
                text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cell_xml.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        sheet_rows.append(f"<row r=\"{row_idx}\">{''.join(cell_xml)}</row>")

    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>'''
    workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Excel</Application></Properties>'''
    core_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>SignalDesk</dc:creator><cp:lastModifiedBy>SignalDesk</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:modified></cp:coreProperties>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

    xlsx_buffer = io.BytesIO()
    with zipfile.ZipFile(xlsx_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        )
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/styles.xml", styles_xml)
    return xlsx_buffer.getvalue()
