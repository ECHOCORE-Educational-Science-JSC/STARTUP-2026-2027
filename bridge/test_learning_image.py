"""Visual vocabulary tool tests without network or robot hardware."""

import asyncio
import base64
import json
import unittest
from unittest.mock import patch, MagicMock

import bridge
import learning_image


class LearningImageTest(unittest.TestCase):
    def test_dragon_fruit_rejects_bat_result(self):
        response = {"query": {"pages": [
            {"title": "Fruit bat", "thumbnail": {"source": "https://img/bat.jpg"}},
            {"title": "Pitaya", "thumbnail": {"source": "https://img/pitaya.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response).encode()):
            self.assertEqual(learning_image.find_thumbnail("quả thanh long")[1], "Pitaya")

    def test_unrelated_picture_is_rejected(self):
        response = {"query": {"pages": [
            {"title": "Fruit bat", "thumbnail": {"source": "https://img/bat.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response).encode()):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.find_thumbnail("dragon fruit")

    def test_visual_verification_fails_closed(self):
        for verdict in [{"matches_subject": False, "suitable_for_child": True},
                        {"matches_subject": "true", "suitable_for_child": True},
                        {"matches_subject": True, "suitable_for_child": False}, {}]:
            with self.subTest(verdict=verdict):
                response = MagicMock()
                response.__enter__.return_value.read.return_value = json.dumps({"candidates": [{
                    "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(verdict)}]}
                }]}).encode()
                with patch.object(learning_image, "urlopen", return_value=response):
                    with self.assertRaises(learning_image.LearningImageError):
                        learning_image.verify_image_subject(b"bat pixels", "dragon fruit", "thanh long", "test")

    def test_visual_verification_sends_actual_pixels(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "matches_subject": True, "suitable_for_child": True})}]}
        }]}).encode()
        with patch.object(learning_image, "urlopen", return_value=response) as send:
            learning_image.verify_image_subject(b"fruit pixels", "dragon fruit", "thanh long", "test")
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(base64.b64decode(body["contents"][0]["parts"][1]["inlineData"]["data"]), b"fruit pixels")

    def test_verifier_unavailable_rejects_image(self):
        with patch.object(learning_image, "urlopen", side_effect=TimeoutError):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.verify_image_subject(b"png", "apple", "apple", "test")

    def test_noise_gate_learns_fan_and_waits_for_voice(self):
        state = bridge.new_speech_state()
        for _ in range(10):
            self.assertFalse(bridge.voice_onset_detected(state, 1400))
        self.assertFalse(bridge.voice_onset_detected(state, 5000))
        self.assertTrue(bridge.voice_onset_detected(state, 5200))

    def test_find_thumbnail_uses_first_page_with_https_image(self):
        response = {"query": {"pages": [
            {"title": "No picture"},
            {"title": "Apple", "thumbnail": {"source": "https://img/apple.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url",
                          return_value=json.dumps(response).encode()):
            url, title = learning_image.find_thumbnail("red apple fruit")
        self.assertEqual(url, "https://img/apple.jpg")
        self.assertEqual(title, "Apple")

    def test_prepare_learning_image_downloads_and_converts(self):
        with patch.object(learning_image, "find_thumbnail",
                          return_value=("https://img/apple.jpg", "Apple")), \
             patch.object(learning_image, "_read_url", return_value=b"jpeg"), \
             patch.object(learning_image, "make_small_png", return_value=b"\x89PNG\r\n\x1a\nsmall"), \
             patch.object(learning_image, "verify_image_subject") as verify:
            result = learning_image.prepare_learning_image("apple")
        verify.assert_called_once_with(result["png"], "apple", "", "")
        self.assertEqual(result["source_title"], "Apple")
        self.assertTrue(result["png"].startswith(b"\x89PNG"))

    def test_find_thumbnail_searches_english_word_when_query_is_vietnamese(self):
        response_dog = {"query": {"pages": [
            {"title": "Dog", "thumbnail": {"source": "https://img/dog.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response_dog).encode()) as read_mock:
            url, title = learning_image.find_thumbnail("con chó", word="dog")
            self.assertEqual(url, "https://img/dog.jpg")
            self.assertEqual(title, "Dog")
            self.assertIn("en.wikipedia.org", read_mock.call_args[0][0])
            self.assertIn("dog", read_mock.call_args[0][0])

    def test_find_thumbnail_searches_vietnamese_wiki_for_pure_vietnamese_topic(self):
        response_tiger = {"query": {"pages": [
            {"title": "Hổ", "thumbnail": {"source": "https://img/tiger.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response_tiger).encode()) as read_mock:
            url, title = learning_image.find_thumbnail("con hổ")
            self.assertEqual(url, "https://img/tiger.jpg")
            self.assertEqual(title, "Hổ")
            self.assertIn("vi.wikipedia.org", read_mock.call_args[0][0])

    def test_make_small_png_produces_compact_png(self):
        import io
        from PIL import Image
        img = Image.new("RGB", (640, 480), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        png = learning_image.make_small_png(buf.getvalue())
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLessEqual(len(png), learning_image.MAX_PNG_BYTES)
        out = Image.open(io.BytesIO(png))
        self.assertEqual(out.size, (320, 240))



class LearningImageToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_lesson_visual_triggers_one_bounded_correction(self):
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({"serverContent": {
                        "inputTranscription": {"text": "Dạy tiếng Anh cho bé đi"},
                        "outputTranscription": {"text": "Apple nghĩa là quả táo."},
                        "turnComplete": True,
                    }})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()
            async def send(self, value): self.sent.append(json.loads(value))

        class Device:
            async def send(self, _value): pass

        class Controller:
            def is_active(self): return False
            def is_playing(self): return False
            async def schedule_pending(self): pass

        gemini = Gemini()
        await bridge.gemini_output(
            gemini, Device(), None, None, "session", 1,
            {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
            music_controller=Controller(),
        )
        corrections = [message for message in gemini.sent if "clientContent" in message]
        self.assertEqual(len(corrections), 1)
        text = corrections[0]["clientContent"]["turns"][0]["parts"][0]["text"]
        self.assertIn("show_learning_image", text)
        self.assertIn("apple", text.casefold())

    async def test_false_spanish_response_from_noise_is_never_played(self):
        class Gemini:
            def __aiter__(self):
                async def events():
                    yield json.dumps({"serverContent": {
                        "inputTranscription": {"text": ""},
                        "outputTranscription": {"text": "Mình không hiểu tiếng Tây Ban Nha."},
                        "modelTurn": {"parts": [{"inlineData": {
                            "data": base64.b64encode(b"audio").decode(),
                        }}]},
                        "turnComplete": True,
                    }})
                return events()

        class Device:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(value)

        class Controller:
            def is_active(self):
                return False

            async def schedule_pending(self): pass

        device = Device()
        await bridge.gemini_output(
            Gemini(), device, None, None, "session", 1,
            {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
            music_controller=Controller(),
        )
        self.assertEqual(device.sent, [])

    async def test_tool_sends_png_to_robot_and_returns_teaching_instruction(self):
        class Gemini:
            def __init__(self):
                self.sent = []

            def __aiter__(self):
                async def events():
                    yield json.dumps({"toolCall": {"functionCalls": [{
                        "id": "visual-one", "name": "show_learning_image",
                        "args": {"word": "apple", "query": "red apple fruit isolated"},
                    }]}})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()

            async def send(self, value):
                self.sent.append(json.loads(value))

        class Device:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(json.loads(value))

        class Controller:
            def is_active(self):
                return False

            async def schedule_pending(self): pass

        gemini, device = Gemini(), Device()
        png = b"\x89PNG\r\n\x1a\nsmall"
        with patch.object(learning_image, "prepare_learning_image",
                          return_value={"png": png, "source_title": "Apple", "source_url": "https://img"}):
            await bridge.gemini_output(
                gemini, device, None, None, "session", 1,
                {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
                music_controller=Controller(),
            )
        visual = device.sent[0]
        self.assertEqual(visual["type"], "learning_image")
        self.assertEqual(visual["word"], "apple")
        self.assertEqual(base64.b64decode(visual["data"]), png)
        response = gemini.sent[0]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["id"], "visual-one")
        self.assertIn("now visible", response["response"]["result"])

    async def test_idle_prompt_fires_once_and_waits_for_user(self):
        class Gemini:
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(json.loads(value))

        class Controller:
            def is_active(self):
                return False

            def is_active(self): return False

        gemini = Gemini()
        stats = {
            "last_user_activity_at": 0.0,
            "proactive_sent_since_user": False,
            "assistant_speaking": False,
        }
        task = asyncio.create_task(bridge.proactive_idle_loop(
            gemini, stats, bridge.new_speech_state(), Controller(),
            idle_after=0.0, check_every=0.01,
        ))
        await asyncio.sleep(0.035)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(len(gemini.sent), 1)
        prompt = gemini.sent[0]["clientContent"]["turns"][0]["parts"][0]["text"]
        self.assertIn("educator", prompt)


if __name__ == "__main__":
    unittest.main()
