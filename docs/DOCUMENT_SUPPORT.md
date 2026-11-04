# Files, complete books and original previews



## Reading an uploaded file

Open a file in **My vault**. **Original** shows the complete uploaded PDF or image. Text and data formats display as plain text. Word, PowerPoint, Excel, OpenDocument and RTF files receive a private PDF rendering that preserves the document layout as well as the converter supports it. **Download original** always returns the original uploaded bytes. **Open full view** opens the preview in a separate browser tab.

The **Extracted text** tab has previous/next, section jump and last-section controls. Each section renders up to 20,000 **characters** to keep long books responsive; this is not a word limit or a limit on the saved document. The reader displays the total extracted word count, searchable passages and pages with indexed text. Blank pages remain in the original but do not count as indexed text pages. Office page references represent slides or sheets; DOCX and RTF extraction does not supply layout page numbers.

Metadata editing changes the title and tags without sending a large book back through the note editor. The original upload is preserved after renaming.

## Supported formats

| Files | Searchable text | Original view |
|---|---|---|
| PDF | Native text plus English OCR for displayed images, including pages with a native header/footer | Complete uploaded PDF |
| DOCX, DOC | Body, tables, headers, footers, notes and supported embedded HTML/plain-text/RTF imports; legacy DOC uses the local converter | Local PDF rendering; download retains DOCX/DOC |
| PPTX, PPT | All slides, speaker notes, chart values and supported diagram text; legacy PPT uses the local converter | Local PDF rendering; download retains presentation |
| XLSX, XLS | All sheets, cell addresses, values and formulas with saved cached values | Local PDF rendering using workbook print settings; all cells remain in extracted text and original download |
| ODT, ODP, ODS | OpenDocument text, presentations and spreadsheets | Local PDF rendering |
| EPUB | HTML chapters in reading order, including remaining text appendices | Download in an EPUB reader; extracted text available in the app |
| RTF | Text and Unicode characters | Local PDF rendering |
| TXT, MD, CSV, TSV, JSON, XML, YAML, YML, LOG | Complete decoded text | Plain text |
| HTML, HTM | Readable text, excluding scripts/styles/templates | Safe plain text source |
| PNG, JPG, JPEG, WEBP | English OCR | Original image |

This is 27 file extensions. Arbitrary binaries, archives, video/audio and encrypted documents are not supported for text indexing. File validation rejects unsupported or malformed uploads explicitly. Office embedded images, audio/video, handwriting and charts are not guaranteed to become searchable text; their original content is retained. PDF/image OCR quality depends on resolution, language and legibility. No extraction system guarantees that every visual element is accurately interpreted.

## Complete storage and explicit limits

Files are not silently shortened. The uploaded bytes are saved before indexing. Extraction or indexing failures leave that original available, with an error and retry action; a failed replacement index keeps the previous passages. Embedding work runs in batches, and the new index is committed only after all batches succeed.

| Limit | Current default |
|---|---:|
| One upload | 100 MiB (shown as 100 MB in the UI) |
| Account storage | 500 MiB |
| Pages / slides / sheets / EPUB text sections | 3,000 |
| Extracted text | 20,000,000 characters |
| Searchable passages per document | 25,000 |
| PDF pages requiring OCR | 1,000 |
| One OCR call | 30 seconds |
| Expanded document ZIP package / single member | 256 MiB / 64 MiB |
| Local Office conversion | 180 seconds / 150 MiB output |

Backend limits can be configured with `MAX_UPLOAD_MB`, `MAX_DOCUMENT_PAGES`, `MAX_EXTRACTED_CHARS`, `MAX_DOCUMENT_CHUNKS`, `MAX_OCR_PAGES` and `DOCUMENT_JOB_TIMEOUT_SECONDS`. Raising the upload limit also requires updating the web picker limit and Next.js proxy body size. Limits remain finite to avoid exhausting the local machine. Typed notes retain their separate 200,000-character editing limit.

Search considers the full eligible SQLite passage set, rather than cutting off at the first 5,000 semantic or 1,500 keyword candidates. Answers still use retrieved passages within the model's context window. Saving an entire book does not mean every page is sent to the AI for each question. The insights panel reports its own source coverage.


## Local Office runtime

Install LibreOffice and make `soffice` available on PATH, or set `LIBREOFFICE_CMD` to its executable in the API environment. On Windows, the launcher reads this setting from `.env.local`. Restart the API after changing it.

The first Office preview runs a local conversion with a private temporary profile. The API caches the resulting PDF privately and checks ownership for subsequent requests. Downloading the original returns the uploaded file in its original format.
