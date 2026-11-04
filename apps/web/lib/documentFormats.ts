export const DOCUMENT_FORMATS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'odt', 'ods', 'odp', 'epub', 'rtf', 'txt', 'md', 'csv', 'tsv', 'json', 'xml', 'html', 'htm', 'yaml', 'yml', 'log', 'png', 'jpg', 'jpeg', 'webp'] as const;
export const DOCUMENT_ACCEPT = DOCUMENT_FORMATS.map(format => `.${format}`).join(',');
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
