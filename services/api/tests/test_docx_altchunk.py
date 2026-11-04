"""Regression coverage for full DOCX imported-content extraction."""
import io
import zipfile
from xml.sax.saxutils import escape

import pytest
from app import document_formats as formats

W = formats.W
R = formats.R
REL = formats.REL
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def paragraph(value):
    return '<w:p><w:r><w:t>' + escape(value) + '</w:t></w:r></w:p>'


def fixture_docx(*, name='body.html', data=b'<p>Imported middle content</p>', mime='text/html',
                 relationship=True, include_part=True, external=False, reference='import1',
                 relationship_type=R + '/aFChunk', extras=None, body=None):
    output = io.BytesIO()
    body = body if body is not None else paragraph('Before import') + '<w:altChunk r:id="' + reference + '"/>' + paragraph('After import')
    document = f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>'
    mode = ' TargetMode="External"' if external else ''
    rel = f'<Relationships xmlns="{REL}"><Relationship Id="import1" Type="{relationship_type}" Target="{escape(name)}"{mode}/></Relationships>'
    content_types = f'<Types xmlns="{CT}"><Override PartName="/word/{escape(name)}" ContentType="{escape(mime)}"/></Types>'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', document)
        if relationship: archive.writestr('word/_rels/document.xml.rels', rel)
        if include_part and not external: archive.writestr('word/' + name, data)
        archive.writestr('[Content_Types].xml', content_types)
        for path, content in (extras or {}).items(): archive.writestr(path, content)
    return output.getvalue()


def read(data):
    return formats.extract_other(data, 'docx')[0][1]


def test_altchunk_html_is_read_once_in_document_order_with_existing_parts():
    wrap = lambda content: f'<w:root xmlns:w="{W}">{paragraph(content)}</w:root>'
    source = fixture_docx(data=b'<html><body><p>Imported middle content</p><script>do not index script</script></body></html>',
                         extras={'word/header1.xml': wrap('Header detail'), 'word/footnotes.xml': wrap('Footnote detail')})
    text = read(source)
    assert text.index('Before import') < text.index('Imported middle content') < text.index('After import')
    assert text.count('Imported middle content') == 1
    assert text.count('Header detail') == 1 and text.count('Footnote detail') == 1
    assert 'do not index script' not in text


@pytest.mark.parametrize(('name', 'mime', 'raw', 'expected'), [
    ('body.dat', 'text/html', b'<p>Mime type chooses HTML</p>', 'Mime type chooses HTML'),
    ('body.xhtml', 'application/xhtml+xml', b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>XHTML body</p></body></html>', 'XHTML body'),
    ('body.txt', 'text/plain', 'Caf\u00e9 UTF-8 text'.encode('utf-8'), 'Caf\u00e9 UTF-8 text'),
    ('body.txt', 'text/plain', 'Unicode \u7814\u7a76'.encode('utf-16'), 'Unicode \u7814\u7a76'),
    ('body.rtf', 'application/rtf', br'{\rtf1\ansi Caf\u233? research}', 'Caf\u00e9 research'),
])
def test_altchunk_supported_local_encodings_and_media_types(name, mime, raw, expected):
    assert expected in read(fixture_docx(name=name, mime=mime, data=raw))


@pytest.mark.parametrize(('changes', 'message'), [
    ({'relationship': False}, 'missing reference'),
    ({'reference': 'unknown'}, 'missing'),
    ({'include_part': False}, 'missing from the package'),
    ({'external': True, 'name': 'https://example.test/book.html'}, 'External imported DOCX'),
    ({'name': 'body.docx', 'mime': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}, 'Unsupported DOCX imported content'),
    ({'relationship_type': R + '/hyperlink'}, 'Unsupported DOCX imported-content reference'),
    ({'name': 'body.rtf', 'mime': 'application/rtf', 'data': b'not RTF'}, 'RTF content is invalid'),
])
def test_altchunk_missing_external_or_unsupported_content_fails_instead_of_partial_text(changes, message):
    with pytest.raises(ValueError, match=message):
        read(fixture_docx(**changes))


def test_docx_nested_textbox_is_not_duplicated():
    body = ('<w:p><w:r><w:t>Main paragraph</w:t></w:r><w:r><w:drawing><w:txbxContent>'
            + paragraph('Text box detail') + '</w:txbxContent></w:drawing></w:r></w:p>')
    text = read(fixture_docx(body=body))
    assert text.count('Main paragraph') == 1
    assert text.count('Text box detail') == 1


def test_altchunk_aggregate_limit_fails_instead_of_returning_prefix(monkeypatch):
    monkeypatch.setattr(formats.config, 'MAX_EXTRACTED_CHARS', 50)
    with pytest.raises(ValueError, match='extraction limit'):
        read(fixture_docx(data=b'<p>' + b'A' * 30 + b'</p>'))


def test_altchunk_path_traversal_fails_before_reading_content():
    with pytest.raises(ValueError, match='Invalid internal document reference'):
        read(fixture_docx(name='../../body.html', include_part=False))


def test_altchunk_inside_textbox_is_preserved_once():
    body = ('<w:p><w:r><w:t>Main paragraph</w:t></w:r><w:r><w:drawing><w:txbxContent>'
            '<w:altChunk r:id="import1"/></w:txbxContent></w:drawing></w:r></w:p>')
    text = read(fixture_docx(body=body))
    assert text.count('Main paragraph') == 1
    assert text.count('Imported middle content') == 1
