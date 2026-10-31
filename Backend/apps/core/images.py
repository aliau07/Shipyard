"""Screenshot processing: every upload is re-encoded, which strips EXIF data such as GPS location."""
from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_SIZE = (1600, 1600)
THUMBNAIL_SIZE = (400, 300)
ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'MPO'}


def _encode_jpeg(image, size):
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    copy.save(buffer, format='JPEG', quality=85, optimize=True)
    return buffer.getvalue()


def validate_image(uploaded_file):
    """Reject files that are too big, aren't images, or are in an unsupported format."""
    limit = settings.MAX_ATTACHMENT_SIZE_MB
    if uploaded_file.size > limit * 1024 * 1024:
        raise ValidationError(f'"{uploaded_file.name}" is larger than {limit} MB.')
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError(f'"{uploaded_file.name}" is not a valid image.')
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError(f'"{uploaded_file.name}" must be a JPEG, PNG or WebP image.')


def process_upload(uploaded_file):
    """Return (image ContentFile, thumbnail ContentFile): upright, metadata-free JPEGs with random names."""
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
    stem = uuid4().hex
    return (
        ContentFile(_encode_jpeg(image, MAX_IMAGE_SIZE), name=f'{stem}.jpg'),
        ContentFile(_encode_jpeg(image, THUMBNAIL_SIZE), name=f'{stem}-thumb.jpg'),
    )
