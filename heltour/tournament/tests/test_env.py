import os
import tempfile

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from heltour.env import SecretFileMapping


class SecretFileMappingTestCase(SimpleTestCase):
    def secret_file(self, contents):
        file = tempfile.NamedTemporaryFile("w", delete=False)
        file.write(contents)
        file.close()
        self.addCleanup(os.unlink, file.name)
        return file.name

    def test_reads_plain_variable(self):
        mapping = SecretFileMapping(env={"SECRET_KEY": "plain"})
        self.assertEqual(mapping["SECRET_KEY"], "plain")

    def test_reads_file_without_its_trailing_newline(self):
        path = self.secret_file("from-file\n")
        mapping = SecretFileMapping(env={"SECRET_KEY_FILE": path})
        self.assertEqual(mapping["SECRET_KEY"], "from-file")

    def test_strips_a_windows_line_ending(self):
        path = self.secret_file("from-file\r\n")
        mapping = SecretFileMapping(env={"SECRET_KEY_FILE": path})
        self.assertEqual(mapping["SECRET_KEY"], "from-file")

    def test_keeps_inner_newlines(self):
        path = self.secret_file("line one\nline two\n")
        mapping = SecretFileMapping(env={"SECRET_KEY_FILE": path})
        self.assertEqual(mapping["SECRET_KEY"], "line one\nline two")

    def test_refuses_variable_and_file_together(self):
        path = self.secret_file("from-file")
        mapping = SecretFileMapping(env={"SECRET_KEY": "plain", "SECRET_KEY_FILE": path})
        with self.assertRaisesMessage(ImproperlyConfigured, "SECRET_KEY and SECRET_KEY_FILE"):
            mapping["SECRET_KEY"]

    def test_missing_variable_raises_key_error(self):
        mapping = SecretFileMapping(env={})
        with self.assertRaises(KeyError):
            mapping["SECRET_KEY"]
