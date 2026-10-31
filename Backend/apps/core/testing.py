"""Helpers shared by every app's tests."""
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image


def image_upload(name='screenshot.png', size=(64, 48), image_format='PNG', colour=(40, 90, 160)):
    """A small, real image file as Django receives it from a multipart upload."""
    buffer = BytesIO()
    Image.new('RGB', size, colour).save(buffer, format=image_format)
    content_type = 'image/png' if image_format == 'PNG' else f'image/{image_format.lower()}'
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class TemporaryMediaMixin:
    """Store uploaded files in a temporary folder that is removed after each test."""

    def setUp(self):
        super().setUp()
        folder = tempfile.mkdtemp(prefix='shipyard-media-')
        override = override_settings(MEDIA_ROOT=folder)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, folder, True)
