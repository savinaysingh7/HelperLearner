from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .forms import AttachmentUploadForm


class AttachmentUploadFormTests(TestCase):
    def test_attachment_form_accepts_supported_extension(self):
        upload = SimpleUploadedFile('build-log.txt', b'Build completed successfully.')
        form = AttachmentUploadForm(
            data={'caption': 'CI output'},
            files={'file': upload},
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_attachment_form_rejects_executable_extension(self):
        upload = SimpleUploadedFile('payload.exe', b'MZ...')
        form = AttachmentUploadForm(
            data={'caption': 'unsafe'},
            files={'file': upload},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Unsupported file type', form.errors['file'][0])

    @override_settings(ATTACHMENT_MAX_UPLOAD_MB=1)
    def test_attachment_form_rejects_oversized_files(self):
        upload = SimpleUploadedFile('huge.log', b'a' * (1024 * 1024 + 1))
        form = AttachmentUploadForm(
            data={'caption': 'too large'},
            files={'file': upload},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Maximum allowed size is 1 MB', form.errors['file'][0])
