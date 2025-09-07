from django.test import SimpleTestCase

from heltour.api_worker.views import _clean


class HelpersTestCase(SimpleTestCase):
    def test_clean(self):
        self.assertEqual(_clean("lip_CSh4NzWorZZKQZKkiTuc"), "lip_***")
        self.assertEqual(_clean("liu_dKvawsUqOEyGU2EDno1x"), "liu_***")
        self.assertEqual(_clean("lio_XFy7kli0rzdTfn1WtVkG"), "lio_***")
        self.assertEqual(
            _clean(
                 "liu_dKvawsUqOEyGU2EDno1x:lio_XFy7kli0rzdTfn1WtVkG,"
                 "lip_CSh4NzWorZZKQZKkiTuc:lio_XFy7kli0rzdTfn1WtVkG"
            ),
            "liu_***:lio_***,lip_***:lio_***",
        )
