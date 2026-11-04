"""Local text extraction for document containers. Never executes document content."""
import io
import json
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from . import config

TEXT_FORMATS = {'txt', 'md', 'csv', 'tsv', 'json', 'xml', 'yaml', 'yml', 'log', 'html', 'htm'}
PACKAGE_FORMATS = {'docx', 'pptx', 'xlsx', 'odt', 'ods', 'odp', 'epub'}
LEGACY_FORMATS = {'doc', 'ppt', 'xls'}
IMAGE_FORMATS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED = TEXT_FORMATS | PACKAGE_FORMATS | LEGACY_FORMATS | IMAGE_FORMATS | {'pdf', 'rtf'}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
TEXT = 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'
TABLE = 'urn:oasis:names:tc:opendocument:xmlns:table:1.0'
DRAW = 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0'
OFFICE = 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024


def text_limit():
    return config.MAX_EXTRACTED_CHARS


def bounded_text(text):
    if len(text) > text_limit():
        raise ValueError(f'Extracted text exceeds {text_limit():,} characters. The original is preserved; nothing was partially indexed.')
    return text


def checked_pages(pages):
    if len(pages) > config.MAX_DOCUMENT_PAGES:
        raise ValueError(f'This document exceeds the configured {config.MAX_DOCUMENT_PAGES:,} page/slide/sheet limit. The original is preserved.')
    if sum(len(text) for _, text in pages) > text_limit():
        raise ValueError(f'Extracted text exceeds {text_limit():,} characters. The original is preserved; nothing was partially indexed.')
    if not any(text.strip() for _, text in pages):
        raise ValueError('No readable text was found. The original is preserved and can still be viewed or downloaded.')
    return pages


def decode_text(data):
    try:
        text = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError:
        raise ValueError('Use UTF-8 text or UTF-16 text with a byte-order mark.') from None
    if '\x00' in text:
        raise ValueError('Binary content is not a text document.')
    return text


def xml(data):
    # ElementTree does not retrieve external entities. Reject declarations too,
    # so user-controlled XML cannot expand internal entities or load a DTD.
    compact = data.replace(b'\x00', b'') if isinstance(data, bytes) else data
    pattern = br'<!\s*(?:DOCTYPE|ENTITY)\b' if isinstance(compact, bytes) else r'<!\s*(?:DOCTYPE|ENTITY)\b'
    if re.search(pattern, compact, flags=re.I):
        raise ValueError('XML DTD and entity declarations are not supported.')
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise ValueError('The document contains invalid XML.') from None


def package(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        files = archive.infolist()
        names = [item.filename for item in files]
        if len(names) != len(set(names)) or len(names) > 25000:
            raise ValueError('The document package contains duplicate or excessive entries.')
        if sum(item.file_size for item in files) > MAX_PACKAGE_BYTES or any(item.file_size > MAX_MEMBER_BYTES for item in files):
            raise ValueError('Expanded document package exceeds the supported size limit.')
        for item in files:
            path = PurePosixPath(item.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or item.flag_bits & 1:
                raise ValueError('Encrypted or unsafe document packages are not supported.')
        return archive
    except (zipfile.BadZipFile, OSError):
        raise ValueError('The file is not a valid document package.') from None


def read_xml(archive, name):
    try:
        return xml(archive.read(name))
    except KeyError:
        raise ValueError('The document package is missing a required part.') from None


def related_path(base, target):
    target = unquote(target).split('#', 1)[0]
    if '://' in target or target.startswith('//') or '\\' in target:
        raise ValueError('External document references are not indexed.')
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), target)) if not target.startswith('/') else target.lstrip('/')
    if path == '..' or path.startswith('../'):
        raise ValueError('Invalid internal document reference.')
    return path


def relationships(archive, part):
    name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if name not in archive.namelist():
        return {}
    result = {}
    for row in read_xml(archive, name):
        if row.get('TargetMode') == 'External':
            continue
        target = row.get('Target')
        if target:
            result[row.get('Id')] = (related_path(part, target), row.get('Type', ''))
    return result


def validate(data, extension):
    if extension not in ALLOWED:
        raise ValueError('Unsupported file format.')
    if not data:
        raise ValueError('The file is empty.')
    if extension == 'pdf' and not data.startswith(b'%PDF-'):
        raise ValueError('The contents are not a PDF.')
    if extension in LEGACY_FORMATS and not data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        raise ValueError('The contents are not a legacy Office document.')
    if extension == 'rtf' and not data.lstrip().startswith(b'{\\rtf'):
        raise ValueError('The contents are not an RTF document.')
    if extension in TEXT_FORMATS:
        text = decode_text(data)
        if extension == 'json':
            try: json.loads(text)
            except (ValueError, RecursionError): raise ValueError('Use valid JSON.') from None
        if extension == 'xml':
            xml(text)
    if extension in PACKAGE_FORMATS:
        required = {'docx': 'word/document.xml', 'pptx': 'ppt/presentation.xml', 'xlsx': 'xl/workbook.xml',
                    'odt': 'content.xml', 'ods': 'content.xml', 'odp': 'content.xml', 'epub': 'META-INF/container.xml'}[extension]
        with package(data) as archive:
            read_xml(archive, required)
            if extension in {'odt', 'ods', 'odp'}:
                kind = {'odt': 'text', 'ods': 'spreadsheet', 'odp': 'presentation'}[extension]
                if archive.read('mimetype').decode('ascii').strip() != 'application/vnd.oasis.opendocument.' + kind:
                    raise ValueError('The OpenDocument type does not match its filename.')
            if extension == 'epub' and archive.read('mimetype').strip() != b'application/epub+zip':
                raise ValueError('The contents are not an EPUB book.')
    if extension in IMAGE_FORMATS:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError('Image is too large.')
            if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                raise ValueError('Unsupported image content.')
            image.verify()


def paragraph_text(element, namespace):
    lines = []
    for paragraph in element.iter('{' + namespace + '}p'):
        tokens = []
        for node in paragraph.iter():
            local = node.tag.rsplit('}', 1)[-1]
            if local == 't' and node.text:
                tokens.append(node.text)
            elif local == 'tab': tokens.append('\t')
            elif local in {'br', 'cr'}: tokens.append('\n')
        if ''.join(tokens).strip(): lines.append(''.join(tokens))
    return bounded_text('\n'.join(lines))


def _word_import(archive, part, reference):
    """Read one explicitly referenced, local altChunk without executing it."""
    relation_name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if not reference or relation_name not in archive.namelist():
        raise ValueError('DOCX imported content has a missing reference. The original is preserved; nothing was partially indexed.')
    relation = next((node for node in read_xml(archive, relation_name) if node.get('Id') == reference), None)
    if relation is None or not relation.get('Target'):
        raise ValueError('DOCX imported content is missing. The original is preserved; nothing was partially indexed.')
    if relation.get('TargetMode', '').lower() == 'external':
        raise ValueError('External imported DOCX content cannot be indexed. Save a self-contained document and retry; the original is preserved.')
    if not relation.get('Type', '').lower().endswith('/afchunk'):
        raise ValueError('Unsupported DOCX imported-content reference. The original is preserved; nothing was partially indexed.')
    target = related_path(part, relation.get('Target'))
    if target not in archive.namelist():
        raise ValueError('DOCX imported content is missing from the package. The original is preserved; nothing was partially indexed.')
    extension = posixpath.splitext(target)[1].lstrip('.').lower()
    content_type = ''
    if '[Content_Types].xml' in archive.namelist():
        overrides, defaults = {}, {}
        for node in read_xml(archive, '[Content_Types].xml'):
            kind = node.tag.rsplit('}', 1)[-1]
            if kind == 'Override': overrides[unquote(node.get('PartName', '')).lstrip('/')] = node.get('ContentType', '')
            elif kind == 'Default': defaults[node.get('Extension', '').lower()] = node.get('ContentType', '')
        content_type = overrides.get(target, defaults.get(extension, '')).split(';', 1)[0].strip().lower()
    if not content_type:
        content_type = {'html': 'text/html', 'htm': 'text/html', 'xhtml': 'application/xhtml+xml',
                        'txt': 'text/plain', 'rtf': 'application/rtf'}.get(extension, '')
    raw = archive.read(target)
    if content_type in {'text/html', 'application/xhtml+xml'}:
        value = html_text(raw)
    elif content_type == 'text/plain':
        value = decode_text(raw)
    elif content_type in {'application/rtf', 'text/rtf'}:
        if not raw.lstrip().startswith(b'{\\rtf'):
            raise ValueError('DOCX imported RTF content is invalid. The original is preserved.')
        from striprtf.striprtf import rtf_to_text
        value = rtf_to_text(raw.decode('latin-1'), errors='strict')
    else:
        raise ValueError('Unsupported DOCX imported content. Save it as normal DOCX paragraphs or a PDF; the original is preserved.')
    return bounded_text(value)


def _word_blocks(archive, part, node):
    # Emit each paragraph once, including text boxes nested inside its drawing.
    # Walking all descendant paragraphs separately would duplicate their text.
    if node.tag == '{' + W + '}p':
        tokens = []
        for child in node.iter():
            if child.tag == '{' + W + '}t': tokens.append(child.text or '')
            elif child.tag == '{' + W + '}tab': tokens.append('\t')
            elif child.tag in {'{' + W + '}br', '{' + W + '}cr'}: tokens.append('\n')
            elif child is not node and child.tag == '{' + W + '}p': tokens.append('\n')
            elif child.tag == '{' + W + '}altChunk':
                tokens.append('\n' + _word_import(archive, part, child.get('{' + R + '}id')) + '\n')
        if ''.join(tokens).strip(): yield ''.join(tokens)
        return
    if node.tag == '{' + W + '}altChunk':
        yield _word_import(archive, part, node.get('{' + R + '}id'))
        return
    for child in node:
        yield from _word_blocks(archive, part, child)


def docx(archive):
    # Body, headers, footers and notes are read once. Imported content is placed
    # exactly where its altChunk reference appears, never scanned independently.
    names = ['word/document.xml'] + sorted(name for name in archive.namelist()
        if re.fullmatch(r'word/(?:header\d+|footer\d+|footnotes|endnotes)\.xml', name))
    pieces, total = [], 0
    for name in names:
        for text in _word_blocks(archive, name, read_xml(archive, name)):
            total += len(text) + (2 if pieces else 0)
            if total > text_limit():
                raise ValueError('DOCX text exceeds the configured extraction limit. The original is preserved; nothing was partially indexed.')
            pieces.append(text)
    return [(None, '\n\n'.join(pieces))]


def pptx(archive):
    presentation = read_xml(archive, 'ppt/presentation.xml')
    refs = relationships(archive, 'ppt/presentation.xml')
    slides = presentation.findall('.//{' + P + '}sldId')
    if len(slides) > config.MAX_DOCUMENT_PAGES:
        raise ValueError('Presentation exceeds the configured slide limit.')
    result = []
    for number, slide in enumerate(slides, 1):
        try: path = refs[slide.get('{' + R + '}id')][0]
        except KeyError: raise ValueError('A slide reference is missing.') from None
        texts = [paragraph_text(read_xml(archive, path), A)]
        for target, kind in relationships(archive, path).values():
            if kind.endswith('/notesSlide'):
                note = paragraph_text(read_xml(archive, target), A)
                if note.strip(): texts.append('Speaker notes:\n' + note)
            elif kind.endswith('/chart'):
                values = [node.text for node in read_xml(archive, target).iter() if node.tag.rsplit('}', 1)[-1] in {'v', 't'} and node.text]
                if values: texts.append('Chart data:\n' + '\n'.join(values))
            elif kind.endswith('/diagramData'):
                diagram = paragraph_text(read_xml(archive, target), A)
                if diagram.strip(): texts.append('Diagram text:\n' + diagram)
        result.append((number, '\n\n'.join(texts)))
    return result


def xlsx(archive):
    shared = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        shared = [''.join(item.itertext()) for item in read_xml(archive, 'xl/sharedStrings.xml').findall('{' + S + '}si')]
    refs = relationships(archive, 'xl/workbook.xml')
    sheets = read_xml(archive, 'xl/workbook.xml').findall('.//{' + S + '}sheet')
    if len(sheets) > config.MAX_DOCUMENT_PAGES:
        raise ValueError('Workbook exceeds the configured sheet limit.')
    pages = []
    total = 0
    for number, sheet in enumerate(sheets, 1):
        try: path = refs[sheet.get('{' + R + '}id')][0]
        except KeyError: raise ValueError('A worksheet reference is missing.') from None
        rows = ['Sheet: ' + sheet.get('name', str(number))]
        for row in read_xml(archive, path).findall('.//{' + S + '}sheetData/{' + S + '}row'):
            cells = []
            for cell in row.findall('{' + S + '}c'):
                value = cell.findtext('{' + S + '}v', '')
                kind = cell.get('t')
                if kind == 's':
                    try:
                        index = int(value)
                        if index < 0: raise ValueError()
                        value = shared[index]
                    except (ValueError, IndexError): raise ValueError('A shared spreadsheet value is invalid.') from None
                elif kind == 'inlineStr': value = ''.join(node.text or '' for node in cell.iter('{' + S + '}t'))
                elif kind == 'b': value = 'TRUE' if value == '1' else 'FALSE'
                formula = cell.findtext('{' + S + '}f')
                if formula is not None: value = '=' + formula + (' [cached value: ' + value + ']' if value else '')
                if value: cells.append(cell.get('r', '') + ': ' + value)
            if cells:
                line = ' | '.join(cells)
                total += len(line)
                if total > text_limit(): raise ValueError('Workbook exceeds the configured extracted-text limit. Nothing was partially indexed.')
                rows.append(line)
        pages.append((number, '\n'.join(rows)))
    return pages


def odf_text(node):
    result = [node.text or '']
    for child in node:
        if child.tag == '{' + TEXT + '}s':
            count = int(child.get('{' + TEXT + '}c', '1'))
            if not 1 <= count <= text_limit(): raise ValueError('Invalid OpenDocument space repetition.')
            result.append(' ' * count)
        elif child.tag == '{' + TEXT + '}tab': result.append('\t')
        elif child.tag == '{' + TEXT + '}line-break': result.append('\n')
        else: result.append(odf_text(child))
        result.append(child.tail or '')
    return bounded_text(''.join(result))


def odf_paragraphs(node):
    return '\n'.join(odf_text(child) for child in node.iter() if child.tag in {'{' + TEXT + '}p', '{' + TEXT + '}h'})


def odf(archive, extension):
    root = read_xml(archive, 'content.xml')
    if extension == 'odt': return [(None, odf_paragraphs(root))]
    if extension == 'odp':
        return [(i, odf_paragraphs(page)) for i, page in enumerate(root.iter('{' + DRAW + '}page'), 1)]
    pages, total = [], 0
    for number, table in enumerate(root.findall('.//{' + TABLE + '}table'), 1):
        rows = ['Sheet: ' + table.get('{' + TABLE + '}name', str(number))]
        row_number = 1
        for row in table.iter('{' + TABLE + '}table-row'):
            columns, column = [], 1
            for cell in row:
                repeat = int(cell.get('{' + TABLE + '}number-columns-repeated', '1'))
                if not 1 <= repeat <= 1000000: raise ValueError('Invalid spreadsheet column repetition.')
                value = odf_paragraphs(cell)
                if not value:
                    value = next((cell.get('{' + OFFICE + '}' + key) for key in ['value', 'date-value', 'boolean-value', 'string-value', 'time-value'] if cell.get('{' + OFFICE + '}' + key) is not None), '')
                formula = cell.get('{' + TABLE + '}formula')
                if formula: value = formula + (' [cached value: ' + value + ']' if value else '')
                if value:
                    for position in range(column, column + repeat):
                        part = f'Column {position}: {value}'
                        total += len(part)
                        if total > text_limit(): raise ValueError('Workbook exceeds the configured extracted-text limit. Nothing was partially indexed.')
                        columns.append(part)
                column += repeat
            repeat = int(row.get('{' + TABLE + '}number-rows-repeated', '1'))
            if not 1 <= repeat <= 1000000: raise ValueError('Invalid spreadsheet row repetition.')
            if columns:
                line = ' | '.join(columns)
                if total + len(line) * repeat > text_limit(): raise ValueError('Workbook exceeds the configured extracted-text limit. Nothing was partially indexed.')
                total += len(line) * repeat
                rows.extend(f'Row {row_number + offset}: {line}' for offset in range(repeat))
            row_number += repeat
        pages.append((number, '\n'.join(rows)))
    return pages


def html_text(data):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, 'html.parser')
    for element in soup(['script', 'style', 'template']): element.decompose()
    return bounded_text(soup.get_text('\n', strip=True))


def epub(archive):
    container = read_xml(archive, 'META-INF/container.xml')
    rootfile = next((node.get('full-path') for node in container.iter() if node.tag.rsplit('}', 1)[-1] == 'rootfile'), None)
    if not rootfile: raise ValueError('EPUB has no readable package document.')
    package_path = related_path('', rootfile)
    book = read_xml(archive, package_path)
    manifest = {node.get('id'): (related_path(package_path, node.get('href', '')), node.get('media-type')) for node in book.iter() if node.tag.rsplit('}', 1)[-1] == 'item'}
    ordered = []
    for node in book.iter():
        if node.tag.rsplit('}', 1)[-1] == 'itemref':
            entry = manifest.get(node.get('idref'))
            if not entry: raise ValueError('EPUB spine references missing content.')
            if entry[1] in {'application/xhtml+xml', 'text/html'} and entry[0] not in ordered: ordered.append(entry[0])
    ordered += [name for name, mime in manifest.values() if mime in {'application/xhtml+xml', 'text/html'} and name not in ordered]
    if len(ordered) > config.MAX_DOCUMENT_PAGES: raise ValueError('EPUB exceeds the configured chapter limit.')
    if 'META-INF/encryption.xml' in archive.namelist():
        encrypted = read_xml(archive, 'META-INF/encryption.xml')
        if any(node.get('URI') in ordered for node in encrypted.iter()):
            raise ValueError('Encrypted EPUB text cannot be indexed. The original is preserved.')
    return [(index, html_text(archive.read(name))) for index, name in enumerate(ordered, 1)]


def extract_other(data, extension):
    if extension in LEGACY_FORMATS:
        from .office import convert_office
        target = {'doc': 'docx', 'ppt': 'pptx', 'xls': 'xlsx'}[extension]
        return extract_other(convert_office(data, extension, target=target), target)
    if extension in PACKAGE_FORMATS:
        with package(data) as archive:
            if extension == 'docx': pages = docx(archive)
            elif extension == 'pptx': pages = pptx(archive)
            elif extension == 'xlsx': pages = xlsx(archive)
            elif extension == 'epub': pages = epub(archive)
            else: pages = odf(archive, extension)
        return checked_pages(pages)
    if extension == 'rtf':
        from striprtf.striprtf import rtf_to_text
        return checked_pages([(None, rtf_to_text(data.decode('latin-1'), errors='strict'))])
    if extension in {'html', 'htm'}: return checked_pages([(None, html_text(decode_text(data)))])
    return checked_pages([(None, decode_text(data))])
