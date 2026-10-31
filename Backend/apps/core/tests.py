from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .exceptions import DomainError, exception_handler
from .images import process_upload, validate_image
from .testing import image_upload


class HealthTests(APITestCase):
    def test_health_needs_no_login(self):
        self.assertEqual(self.client.get('/api/health/').json(), {'status': 'ok'})

    def test_api_docs_are_served(self):
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_api_needs_a_login(self):
        self.assertEqual(self.client.get('/api/projects/').status_code, 401)


class ImageTests(SimpleTestCase):
    def test_validate_image(self):
        validate_image(image_upload())
        with self.assertRaisesMessage(ValidationError, 'is not a valid image'):
            validate_image(SimpleUploadedFile('x.png', b'nope'))
        with self.assertRaisesMessage(ValidationError, 'must be a JPEG, PNG or WebP image'):
            validate_image(image_upload('x.gif', image_format='GIF'))

    def test_process_upload_gives_random_names(self):
        first, thumb = process_upload(image_upload())
        second, _ = process_upload(image_upload())

        self.assertTrue(first.name.endswith('.jpg') and thumb.name.endswith('-thumb.jpg'))
        self.assertNotEqual(first.name, second.name)


class DomainErrorTests(SimpleTestCase):
    def test_domain_errors_become_responses_with_their_status(self):
        response = exception_handler(DomainError('Nope.', 409), {})

        self.assertEqual((response.status_code, response.data), (409, {'detail': 'Nope.'}))
