import unittest
import os

from unittest import mock

from server.helper.audio import determine_audio_type, extract_browser_audio_labels, get_audio_env


class AudioTests(unittest.TestCase):
    def test_extract_browser_audio_labels_none(self):
        extract_browser_audio_labels({})
        self.assertIsNone(extract_browser_audio_labels({}))

    def test_extract_browser_audio_labels(self):
        extracted_labels = extract_browser_audio_labels({"caps.audio": "foo|bar"})
        self.assertEqual(extracted_labels, ["foo", "bar"])

    def test_get_audio_env_none(self):
        self.assertEqual(get_audio_env(None), {})

    @mock.patch.dict(os.environ,{"AUDIO_TYPE": "MP3", "BAR": "FOO"})
    def test_get_audio_env_type(self):
        self.assertEqual(get_audio_env("OPUS"), {"AUDIO_TYPE": "MP3"})

    @mock.patch.dict(os.environ, {"OPUS_FOO": "BAR", "WEBRTC_STUN_SERVER": "stun://"})
    def test_get_audio_env_specialized(self):
        self.assertEqual(get_audio_env("OPUS"), {"OPUS_FOO": "BAR"})

    @mock.patch.dict(os.environ,{"AUDIO_TYPE": "MP3"})
    def test_determine_audio_type_nothing_match(self):
        requested_sound = "opus"
        browser_tags = {"caps.audio": "webrtc"}
        self.assertEqual(determine_audio_type(requested_sound, browser_tags), None)

    @mock.patch.dict(os.environ,{"AUDIO_TYPE": "foo|bar|opus"})
    def test_determine_audio_type_with_labels(self):
        requested_sound = "foo|bar|opus"
        browser_tags = {"caps.audio": "webrtc|opus"}
        self.assertEqual(determine_audio_type(requested_sound, browser_tags), "opus")

    @mock.patch.dict(os.environ,{"AUDIO_TYPE": "bar|opus"})
    def test_determine_audio_type_without_labels(self):
        requested_sound = "foo|bar"
        browser_tags = {}
        self.assertEqual(determine_audio_type(requested_sound, browser_tags), "bar")
