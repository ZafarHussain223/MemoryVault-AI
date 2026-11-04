"""OCR with a bounded runtime and explicit dependency errors."""
import os
import re


def read_image(image):
    try:
        import pytesseract
        from PIL import ImageOps
    except ImportError:
        raise ValueError('OCR dependencies are unavailable. Install the full API requirements and Tesseract.')
    executable = os.getenv('TESSERACT_CMD')
    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable
    language = os.getenv('OCR_LANGUAGE', 'eng')
    if not re.fullmatch(r'[A-Za-z0-9_+]{1,80}', language):
        raise ValueError('Invalid OCR language configuration.')
    try:
        return pytesseract.image_to_string(ImageOps.exif_transpose(image), lang=language, timeout=30)
    except pytesseract.TesseractNotFoundError:
        raise ValueError('Tesseract is not installed or configured. Set TESSERACT_CMD on the server and retry.')
    except RuntimeError:
        raise ValueError('OCR timed out. Try a smaller or clearer image.')
    except pytesseract.TesseractError:
        raise ValueError('OCR could not read this image. Check installed language data and retry.')
