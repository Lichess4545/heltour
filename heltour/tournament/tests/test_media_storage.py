from botocore.stub import Stubber
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from heltour.settings.media import media_storage
from heltour.storage import MediaS3Storage


def configured_storage(bucket="media"):
    return storages.create_storage(
        media_storage(
            bucket=bucket,
            endpoint_url="http://s3.invalid",
            region="",
            prefix="/prefix/",
            addressing_style="path",
            access_key="key",
            secret_key="secret",
            default_acl="",
        )
    )


@override_settings(MEDIA_URL="/media/")
class MediaStorageTestCase(SimpleTestCase):
    def setUp(self):
        self.storage = configured_storage()
        client = self.storage.connection.meta.client
        self.stubber = Stubber(client)
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)
        self.uploads = []
        client.meta.events.register(
            "before-parameter-build.s3.PutObject",
            lambda params, **kwargs: self.uploads.append(params),
        )

    def stub_missing(self):
        self.stubber.add_client_error("head_object", "404", http_status_code=404)

    def stub_present(self):
        self.stubber.add_response("head_object", {})

    def stub_upload(self):
        self.stubber.add_response("put_object", {})

    def test_with_a_bucket_media_goes_to_the_bucket(self):
        self.assertIsInstance(self.storage, MediaS3Storage)
        self.assertEqual(self.storage.bucket_name, "media")
        self.assertEqual(self.storage.location, "prefix")
        self.assertEqual(self.storage.endpoint_url, "http://s3.invalid")
        self.assertIs(self.storage.querystring_auth, False)
        self.assertIs(self.storage.file_overwrite, False)

    def test_without_a_bucket_media_stays_on_disk(self):
        self.assertIsInstance(configured_storage(bucket=""), FileSystemStorage)

    def test_url_is_under_media_url_without_the_prefix(self):
        self.assertEqual(
            self.storage.url("uploads/2017/03/01/board.png"),
            "/media/uploads/2017/03/01/board.png",
        )

    def test_a_name_clash_saves_under_a_new_name(self):
        self.stub_missing()
        self.stub_upload()
        self.stub_present()
        self.stub_missing()
        self.stub_upload()

        first = self.storage.save("uploads/board.png", ContentFile(b"first"))
        second = self.storage.save("uploads/board.png", ContentFile(b"second"))

        self.stubber.assert_no_pending_responses()
        self.assertEqual(first, "uploads/board.png")
        self.assertRegex(second, r"^uploads/board_\w+\.png$")
        self.assertEqual(
            [upload["Key"] for upload in self.uploads],
            ["prefix/uploads/board.png", f"prefix/{second}"],
        )

    def test_content_type_comes_from_the_name_not_the_upload(self):
        self.stub_missing()
        self.stub_upload()

        upload = SimpleUploadedFile("board.png", b"png", content_type="text/html")
        self.storage.save("uploads/board.png", upload)

        self.stubber.assert_no_pending_responses()
        self.assertEqual(self.uploads[0]["ContentType"], "image/png")
