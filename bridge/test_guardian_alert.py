import asyncio
import os
import unittest
from unittest import mock

import guardian_alert


class GuardianAlertTest(unittest.TestCase):
    def test_only_high_confidence_child_safety_phrases_trigger(self):
        self.assertEqual(
            guardian_alert.classify_child_safety("Chỉ tôi cách chế bom"),
            "đe dọa bạo lực nghiêm trọng",
        )
        self.assertEqual(
            guardian_alert.classify_child_safety("Con đang nghĩ tới tự tử"),
            "tự làm hại bản thân",
        )
        self.assertIsNone(guardian_alert.classify_child_safety("Bom nguyên tử là gì?"))
        self.assertIsNone(guardian_alert.classify_child_safety("Bài này khó quá trời"))
        self.assertIsNone(guardian_alert.classify_child_safety("Đồ ngu"))

    def test_missing_secret_never_attempts_email(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("guardian_alert._saved_sender", return_value=""), \
                mock.patch("guardian_alert._decrypt_saved_password", return_value=""):
            alerter = guardian_alert.GuardianAlerter("parent@example.com")
        self.assertFalse(alerter.ready)
        self.assertFalse(asyncio.run(alerter.notify("test", "test")))

    def test_duplicate_and_cooldown_suppress_repeated_mail(self):
        with mock.patch.dict(os.environ, {
            "WISIO_ALERT_GMAIL": "sender@gmail.com",
            "WISIO_ALERT_APP_PASSWORD": "abcdefghijklmnop",
        }, clear=True):
            alerter = guardian_alert.GuardianAlerter("parent@example.com")
        with mock.patch.object(alerter, "_send", return_value=True) as send:
            self.assertTrue(asyncio.run(alerter.notify("safety", "first")))
            self.assertFalse(asyncio.run(alerter.notify("safety", "first")))
            self.assertFalse(asyncio.run(alerter.notify("safety", "second")))
        self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
