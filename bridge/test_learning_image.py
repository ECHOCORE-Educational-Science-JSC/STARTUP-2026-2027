"""Visual vocabulary tool tests without network or robot hardware."""

import asyncio
import base64
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

import bridge
import learning_image


class LearningImageTest(unittest.TestCase):
    def setUp(self):
        learning_image._IMAGE_CACHE.clear()
        learning_image.clear_verification_backoff()
        self.enterContext(patch.object(learning_image.google_image_search, 'get_api_key', return_value=''))
        self.enterContext(patch.dict(learning_image.os.environ, {'WISIO_IMAGE_SOURCE': 'auto'}))
        self.enterContext(patch.object(learning_image, '_read_cached_image', return_value=None))

    def test_vietnamese_dish_keeps_specific_name_instead_of_generic_food(self):
        response = {"results": [{"title": "Bun bo Hue", "thumbnail": "https://img/bunbo.jpg",
                                 "width": 640, "height": 480, "tags": []}]}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response).encode()) as read:
            results = learning_image.find_openverse_thumbnails("bún bò Huế", "food")
        self.assertEqual(results[0][0], "https://img/bunbo.jpg")
        self.assertIn("source=flickr", read.call_args.args[0])
        self.assertIn("bun+bo+hue", read.call_args.args[0])

    def test_dish_filter_rejects_other_caramelized_food(self):
        response = {"results": [
            {"title": "Caramelized fish Ca kho", "thumbnail": "https://img/fish.jpg"},
            {"title": "Thit kho pork and eggs", "thumbnail": "https://img/pork.jpg"},
        ]}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response).encode()):
            results = learning_image.find_openverse_thumbnails("thịt kho", "food")
        self.assertEqual(results, [("https://img/pork.jpg", "Thit kho pork and eggs")])

    def test_vietnamese_dish_tries_openverse_before_wikipedia(self):
        with patch.object(learning_image, "find_openverse_thumbnails", return_value=[("https://img/pho.jpg", "Pho")]), \
             patch.object(learning_image, "find_thumbnails") as wiki, \
             patch.object(learning_image, "_read_url", return_value=b"image"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject", return_value=None):
            result = learning_image.prepare_learning_image("phở bò", "key", "food")
        wiki.assert_not_called()
        self.assertEqual(result["source_url"], "https://img/pho.jpg")

    def test_precise_query_overrides_stale_word_and_keeps_color(self):
        response = {"query": {"pages": [
            {"title": "Cat", "thumbnail": {"source": "https://img/cat.jpg"}},
            {"title": "Black cat", "thumbnail": {"source": "https://img/black-cat.jpg"}},
        ]}}
        urls = []
        def fake_read(url, *_args, **_kwargs):
            urls.append(url)
            return json.dumps(response).encode()
        with patch.object(learning_image, "_read_url", side_effect=fake_read):
            source, title = learning_image.find_thumbnail("black cat", word="cat")
        self.assertEqual((source, title), ("https://img/black-cat.jpg", "Black cat"))
        self.assertIn("black+cat", urls[0])

    def test_precise_commons_result_skips_slow_fallback_queries(self):
        response = {"query": {"pages": [{
            "title": "File:One orange cat photo.jpg",
            "imageinfo": [{"thumburl": "https://img/orange-cat.jpg"}],
        }]}}
        with patch.object(learning_image, "_read_url",
                          return_value=json.dumps(response).encode()) as read:
            result = learning_image.find_thumbnails("one orange cat photo", word="cat")
        self.assertEqual(result[0], ("https://img/orange-cat.jpg", "One orange cat photo.jpg"))
        read.assert_called_once()

    def test_speech_typo_tom_hop_searches_lobster_in_english_first(self):
        response = {"query": {"pages": [{
            "title": "File:American lobster.jpg",
            "imageinfo": [{"thumburl": "https://img/lobster.jpg",
                           "thumbwidth": 640, "thumbheight": 480}],
        }]}}
        with patch.object(learning_image, "_read_url",
                          return_value=json.dumps(response).encode()) as read:
            source, title = learning_image.find_thumbnail("tôm hốp")
        self.assertEqual((source, title),
                         ("https://img/lobster.jpg", "American lobster.jpg"))
        self.assertIn("gsrsearch=lobster", read.call_args_list[0].args[0])

    def test_landscape_candidate_ranks_above_portrait_candidate(self):
        response = {"query": {"pages": [
            {"title": "File:Lobster portrait.jpg", "imageinfo": [{
                "thumburl": "https://img/portrait.jpg", "thumbwidth": 360,
                "thumbheight": 640}]},
            {"title": "File:Lobster landscape.jpg", "imageinfo": [{
                "thumburl": "https://img/landscape.jpg", "thumbwidth": 640,
                "thumbheight": 480}]},
        ]}}
        with patch.object(learning_image, "_read_url",
                          return_value=json.dumps(response).encode()):
            results = learning_image.find_thumbnails("lobster", limit=2)
        self.assertEqual(results[0][0], "https://img/landscape.jpg")

    def test_new_query_never_reuses_conflicting_old_subject(self):
        response = {"query": {"pages": [
            {"title": "Seafood", "thumbnail": {"source": "https://img/seafood.jpg"}},
            {"title": "Cat", "thumbnail": {"source": "https://img/cat.jpg"}},
        ]}}
        urls = []
        def fake_read(url, *_args, **_kwargs):
            urls.append(url)
            return json.dumps(response).encode()
        with patch.object(learning_image, "_read_url", side_effect=fake_read):
            source, title = learning_image.find_thumbnail("seafood", word="cat")
        self.assertEqual((source, title), ("https://img/seafood.jpg", "Seafood"))
        self.assertNotIn("cat", urls[0].casefold())

    def test_prepare_never_serves_unverified_picture(self):
        with patch.object(learning_image, "find_thumbnails", return_value=[("https://img/cat.jpg", "Cat")]), \
             patch.object(learning_image, "_read_url", return_value=b"image"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject", side_effect=learning_image.LearningImageError("wrong")):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.prepare_learning_image("black cat", "key", "cat")

    def test_prepare_uses_openverse_after_wikimedia_candidates_fail(self):
        candidates = [("https://wiki/bad.jpg", "Wrong animal")]
        alternatives = [("https://openverse/cat.jpg", "Orange cat photo")]
        with patch.object(learning_image, "find_thumbnails", return_value=candidates), \
             patch.object(learning_image, "find_openverse_thumbnails", return_value=alternatives), \
             patch.object(learning_image, "_read_url", return_value=b"image"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject",
                          side_effect=[learning_image.LearningImageError("wrong"), None]):
            result = learning_image.prepare_learning_image(
                "orange cat photo", "key", "cat")
        self.assertEqual(result["source_url"], "https://openverse/cat.jpg")

    def test_prepare_rejects_even_matching_filename_when_pixel_verifier_is_offline(self):
        with patch.object(learning_image, "find_thumbnails",
                          return_value=[("https://img/orange-cat.jpg", "One orange cat photo.jpg")]), \
             patch.object(learning_image, "_read_url", return_value=b"image"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject",
                          side_effect=learning_image.ImageVerificationUnavailable("timeout")):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.prepare_learning_image(
                    "one orange cat photo", "configured-key", "cat")

    def test_metadata_fallback_rejects_wrong_subject(self):
        with patch.object(learning_image, "find_thumbnails",
                          return_value=[("https://img/meat.jpg", "Braised pork.jpg")]), \
             patch.object(learning_image, "_read_url", return_value=b"image"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject",
                          side_effect=learning_image.ImageVerificationUnavailable("timeout")):
            with self.assertRaises(learning_image.LearningImageError):
                learning_image.prepare_learning_image(
                    "lobster underwater animal", "configured-key", "lobster")

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
        valid_shape = {"landscape_fit": True, "subject_fully_visible": True,
                       "matches_attributes": True, "matches_image_type": True}
        for verdict in [{"matches_subject": False, "suitable_for_child": True, **valid_shape},
                        {"matches_subject": "true", "suitable_for_child": True, **valid_shape},
                        {"matches_subject": True, "suitable_for_child": False, **valid_shape},
                        {"matches_subject": True, "suitable_for_child": True,
                         **valid_shape, "matches_attributes": False},
                        {"matches_subject": True, "suitable_for_child": True,
                         **valid_shape, "matches_image_type": False},
                        {"matches_subject": True, "suitable_for_child": True,
                         "landscape_fit": False, "subject_fully_visible": True}, {}]:
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
                "matches_subject": True, "suitable_for_child": True,
                "landscape_fit": True, "subject_fully_visible": True,
                "matches_attributes": True, "matches_image_type": True})}]}
        }]}).encode()
        with patch.object(learning_image, "urlopen", return_value=response) as send:
            learning_image.verify_image_subject(b"fruit pixels", "dragon fruit", "thanh long", "test")
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(base64.b64decode(body["contents"][0]["parts"][1]["inlineData"]["data"]), b"fruit pixels")

    def test_verifier_sees_constraints_after_120_characters(self):
        query = "cat in a landscape scene " + "with surrounding trees " * 6 + "with orange fur, a photo"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "matches_subject": True, "matches_attributes": True, "matches_image_type": True,
                "suitable_for_child": True, "landscape_fit": True, "subject_fully_visible": True})}]}
        }]}).encode()
        with patch.object(learning_image, "urlopen", return_value=response) as send:
            learning_image.verify_image_subject(b"pixels", query, "cat", "test")
        body = json.loads(send.call_args.args[0].data)
        self.assertIn(query, body["contents"][0]["parts"][0]["text"])

    def test_expired_image_deadline_does_not_start_another_download(self):
        with patch.object(learning_image.time, "monotonic", return_value=20), \
             patch.object(learning_image, "urlopen") as download:
            learning_image._IMAGE_OPERATION.deadline = 19
            try:
                with self.assertRaises(learning_image.LearningImageError):
                    learning_image._read_url("https://img/cat.jpg", 1024)
                download.assert_not_called()
            finally:
                del learning_image._IMAGE_OPERATION.deadline

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
        with patch.object(learning_image, "find_thumbnails",
                          return_value=[("https://img/apple.jpg", "Apple")]), \
             patch.object(learning_image, "_read_url", return_value=b"jpeg"), \
             patch.object(learning_image, "make_small_png", return_value=b"\x89PNG\r\n\x1a\nsmall"), \
             patch.object(learning_image, "verify_image_subject") as verify:
            result = learning_image.prepare_learning_image("apple")
        verify.assert_called_once_with(result["png"], "apple", "", "")
        self.assertEqual(result["source_title"], "Apple")
        self.assertTrue(result["png"].startswith(b"\x89PNG"))

    def test_prepare_retries_until_pixels_match_exact_subject(self):
        candidates = [("https://img/wrong.jpg", "White cat"),
                      ("https://img/right.jpg", "Black cat")]
        with patch.object(learning_image, "find_thumbnails", return_value=candidates), \
             patch.object(learning_image, "_read_url", side_effect=[b"wrong", b"right"]), \
             patch.object(learning_image, "make_small_png", side_effect=[b"png1", b"png2"]), \
             patch.object(learning_image, "verify_image_subject", side_effect=[
                 learning_image.LearningImageError("wrong color"), None]) as verify:
            result = learning_image.prepare_learning_image("black cat", "key", "cat")
        self.assertEqual(result["source_title"], "Black cat")
        self.assertEqual(verify.call_count, 2)

    def test_prepare_caches_verified_lesson_image(self):
        with patch.object(learning_image, "find_thumbnails",
                          return_value=[("https://img/cat.jpg", "Orange cat photo")]) as find, \
             patch.object(learning_image, "_read_url", return_value=b"jpeg"), \
             patch.object(learning_image, "make_small_png", return_value=b"png"), \
             patch.object(learning_image, "verify_image_subject"):
            first = learning_image.prepare_learning_image("one orange cat photo", "key", "cat")
            second = learning_image.prepare_learning_image("one orange cat photo", "key", "cat")
        self.assertEqual(first, second)
        find.assert_called_once()

    def test_find_thumbnail_searches_english_word_when_query_is_vietnamese(self):
        response_dog = {"query": {"pages": [
            {"title": "Dog", "thumbnail": {"source": "https://img/dog.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response_dog).encode()) as read_mock:
            url, title = learning_image.find_thumbnail("con chó", word="dog")
            self.assertEqual(url, "https://img/dog.jpg")
            self.assertEqual(title, "Dog")
        called_urls = [call.args[0] for call in read_mock.call_args_list]
        self.assertTrue(any("en.wikipedia.org" in url and "dog" in url for url in called_urls))

    def test_find_thumbnail_searches_vietnamese_wiki_for_pure_vietnamese_topic(self):
        response_tiger = {"query": {"pages": [
            {"title": "Hổ", "thumbnail": {"source": "https://img/tiger.jpg"}},
        ]}}
        with patch.object(learning_image, "_read_url", return_value=json.dumps(response_tiger).encode()) as read_mock:
            url, title = learning_image.find_thumbnail("con hổ")
            self.assertEqual(url, "https://img/tiger.jpg")
            self.assertEqual(title, "Hổ")
            self.assertTrue(any("vi.wikipedia.org" in call.args[0]
                                for call in read_mock.call_args_list))

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
    def setUp(self):
        self.enterContext(patch.object(learning_image.google_image_search, 'get_api_key', return_value=''))
        self.enterContext(patch.object(learning_image, '_read_cached_image', return_value=None))

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_tool_success_names_the_authoritative_dish_instead_of_raw_chicken(self):
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {
                        'text': 'Tôi muốn ăn chân gà sả tắc. Cho tôi xem hình.'}}})
                    yield json.dumps({'toolCall': {'functionCalls': [{
                        'id': 'dish', 'name': 'show_learning_image',
                        'args': {'word': 'chicken', 'query': 'chicken photo'}}]}})
                return events()
            async def send(self, text): self.sent.append(json.loads(text))
        class Device:
            def __init__(self): self.sent = []
            async def send(self, text): self.sent.append(json.loads(text))
        class Controller:
            def is_active(self): return False
            def is_playing(self): return False
            async def schedule_pending(self): pass
        gemini, device = Gemini(), Device()
        with patch.object(learning_image, 'prepare_learning_image', return_value={
                'png': b'actual dish PNG', 'verified': True}):
            await bridge.gemini_output(gemini, device, None, None, 's', 1,
                                      {'gemini_content_seen': False}, bridge.new_speech_state(),
                                      music_controller=Controller())
        picture = next(item for item in device.sent if item.get('type') == 'learning_image')
        self.assertEqual(picture['word'], 'chan ga sa tac')
        message = gemini.sent[0]['toolResponse']['functionResponses'][0]['response']['result']
        self.assertNotIn('illustration for chicken is', message)
        self.assertIn('lemongrass', message)

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_verification_failure_is_not_retried_by_tool_correction_or_fallback(self):
        class Loader:
            def schedule(self, items): return len(items)
            async def get(self, *args, **kwargs):
                raise learning_image.ImageVerificationUnavailable('GEMINI_VERIFY_HTTP_503')
            async def close(self): pass
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({'serverContent': {'inputTranscription': {
                        'text': 'Cho xem ảnh con mèo màu cam'}}})
                    call = {'id': 'a', 'name': 'show_learning_image',
                            'args': {'word': 'cat', 'query': 'orange cat'}}
                    yield json.dumps({'toolCall': {'functionCalls': [call]}})
                    yield json.dumps({'toolCall': {'functionCalls': [{**call, 'id': 'b'}]}})
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                    yield json.dumps({'serverContent': {'turnComplete': True}})
                return events()
            async def send(self, text): self.sent.append(json.loads(text))
        class Device:
            def __init__(self): self.sent = []
            async def send(self, text): self.sent.append(json.loads(text))
        class Controller:
            def is_active(self): return False
            def is_playing(self): return False
            async def schedule_pending(self): pass
        loader, gemini, device = Loader(), Gemini(), Device()
        loader.get = AsyncMock(side_effect=loader.get)
        with patch.object(bridge.learning_prefetch, 'LearningImagePrefetch', return_value=loader):
            await bridge.gemini_output(gemini, device, None, None, 's', 1,
                                      {'gemini_content_seen': False}, bridge.new_speech_state(),
                                      music_controller=Controller())
        self.assertEqual(loader.get.await_count, 1)
        self.assertFalse(any('clientContent' in item for item in gemini.sent))
        self.assertFalse(any(item.get('type') == 'learning_image' for item in device.sent))
        replies = [item['toolResponse']['functionResponses'][0]['response']
                   for item in gemini.sent if 'toolResponse' in item]
        self.assertEqual(len(replies), 2)
        self.assertIn('HTTP_503', replies[1]['error'])

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_display_checks_user_color_and_rejects_unrelated_tool_subject(self):
        state = bridge.learning_session.LearningVisualState()
        state.observe_user("Cho xem ảnh một con mèo màu cam dạng hoạt hình")
        loader = MagicMock()
        loader.get = AsyncMock(return_value={"png": b"cat", "verified": True})
        device = MagicMock()
        device.send = AsyncMock()
        await bridge.deliver_learning_image(device, "s", state, "key", "cat", "cat", prefetch=loader)
        exact = loader.get.call_args.args[0]
        for attribute in ("one", "orange", "cat", "cartoon"):
            self.assertIn(attribute, exact)
        device.send.reset_mock()
        loader.get.reset_mock()
        with self.assertRaises(learning_image.LearningImageError):
            await bridge.deliver_learning_image(device, "s", state, "key", "dog", "dog", prefetch=loader)
        device.send.assert_not_called()
        loader.get.assert_not_called()

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_image_preserves_partial_audio_until_turn_end(self):
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {
                        "data": base64.b64encode(b"\0\0").decode(),
                    }}]}}})
                    yield json.dumps({"toolCall": {"functionCalls": [{
                        "id": "cat", "name": "show_learning_image", "args": {"word": "cat", "query": "cat"},
                    }]}})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()
            async def send(self, text): self.sent.append(json.loads(text))
        class Music:
            def is_active(self): return False
            def is_playing(self): return False
            async def defer_for_speech(self): pass
            async def schedule_pending(self): pass
        playback = MagicMock()
        playback.finish = AsyncMock()
        playback.cancel = AsyncMock()
        device = MagicMock()
        device.send = AsyncMock()
        with patch.object(bridge, "PacedPlayback", return_value=playback), \
             patch.object(learning_image, "prepare_learning_image", return_value={"png": b"cat", "verified": True}):
            await bridge.gemini_output(Gemini(), device, None, None, "s", 1,
                                      {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
                                      music_controller=Music())
        playback.put.assert_called_once()
        self.assertEqual(len(playback.put.call_args.args[0]), bridge.OUTPUT_SAMPLES * 2)
        playback.finish.assert_awaited_once()

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_multiple_display_calls_require_explanation_between_images(self):
        cat_ready = asyncio.Event()
        class Loader:
            def schedule(self, items): return len(items)
            async def get(self, query, word, timeout=18):
                return {"png": word.encode(), "verified": True}
            async def close(self): pass
        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    calls = [{"id": w, "name": "show_learning_image", "args": {"word": w, "query": w}}
                             for w in ("cat", "dog")]
                    yield json.dumps({"toolCall": {"functionCalls": calls}})
                    await cat_ready.wait()
                    yield json.dumps({"serverContent": {
                        "outputTranscription": {"text": "Cat nghĩa là con mèo."},
                    }})
                    yield json.dumps({"toolCall": {"functionCalls": [calls[1]]}})
                    yield json.dumps({"serverContent": {
                        "modelTurn": {"parts": [{"inlineData": {"data": "AAA="}}]},
                    }})
                    yield json.dumps({"toolCall": {"functionCalls": [calls[1]]}})
                    yield json.dumps({"serverContent": {"turnComplete": True}})
                return events()
            async def send(self, text):
                value = json.loads(text)
                self.sent.append(value)
                if any(reply.get('id') == 'cat' for reply in value.get('toolResponse', {}).get('functionResponses', [])):
                    cat_ready.set()
        class Device:
            def __init__(self): self.sent = []
            async def send(self, text): self.sent.append(json.loads(text))
        class Music:
            def is_active(self): return False
            def is_playing(self): return False
            async def defer_for_speech(self): pass
        gemini, device = Gemini(), Device()
        playback = MagicMock(finish=AsyncMock(), cancel=AsyncMock())
        with patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=Loader()), \
             patch.object(bridge, "PacedPlayback", return_value=playback):
            await bridge.gemini_output(gemini, device, None, None, "s", 1,
                                      {"gemini_content_seen": False}, bridge.new_speech_state(),
                                      music_controller=Music())
        self.assertEqual([x["word"] for x in device.sent if x["type"] == "learning_image"], ["cat", "dog"])
        dog_replies = [reply['response'] for message in gemini.sent
                       for reply in message.get('toolResponse', {}).get('functionResponses', [])
                       if reply['id'] == 'dog']
        self.assertEqual(len(dog_replies), 3)
        self.assertIn('error', dog_replies[0])
        self.assertIn('error', dog_replies[1])
        self.assertNotIn('error', dog_replies[2])

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_batch_tool_prefetches_without_display_and_reuses_on_each_show(self):
        image_ready = {word: asyncio.Event() for word in ('cat', 'dog')}
        class Loader:
            def __init__(self, key): self.items = []; self.queries = []; self.closed = False
            def schedule(self, items): self.items.extend(items); return len(items)
            async def get(self, query, word, timeout=18):
                self.queries.append((word, query))
                return {"png": word.encode(), "verified": True, "source_title": word}
            async def close(self): self.closed = True

        class Gemini:
            def __init__(self): self.sent = []
            def __aiter__(self):
                async def events():
                    yield json.dumps({"toolCall": {"functionCalls": [{
                        "id": "batch", "name": "prefetch_learning_images", "args": {"items": [
                            {"word": "cat", "query": "cat"}, {"word": "dog", "query": "dog"},
                        ]}}]}})
                    for word in ("cat", "dog"):
                        yield json.dumps({"toolCall": {"functionCalls": [{
                            "id": word, "name": "show_learning_image", "args": {"word": word, "query": word},
                        }]}})
                        await image_ready[word].wait()
                        yield json.dumps({"serverContent": {
                            "outputTranscription": {"text": f"{word} vocabulary."},
                            "modelTurn": {"parts": [{"inlineData": {"data": "AAA="}}]},
                            "turnComplete": True,
                        }})
                return events()
            async def send(self, text):
                value = json.loads(text)
                self.sent.append(value)
                for reply in value.get('toolResponse', {}).get('functionResponses', []):
                    if reply.get('id') in image_ready:
                        image_ready[reply['id']].set()

        class Device:
            def __init__(self): self.sent = []
            async def send(self, text): self.sent.append(json.loads(text))
        class Music:
            def is_active(self): return False
            def is_playing(self): return False
            async def schedule_pending(self): pass
            async def defer_for_speech(self): pass

        loader = Loader("key")
        gemini, device = Gemini(), Device()
        playback = MagicMock(finish=AsyncMock(), cancel=AsyncMock())
        with patch.object(bridge.learning_prefetch, "LearningImagePrefetch", return_value=loader), \
             patch.object(bridge, "PacedPlayback", return_value=playback):
            await bridge.gemini_output(gemini, device, None, None, "session", 1,
                                      {"gemini_content_seen": False}, bridge.new_speech_state(),
                                      music_controller=Music(), image_api_key="key")
        self.assertEqual([item["word"] for item in loader.items], ["cat", "dog"])
        self.assertEqual([item["word"] for item in device.sent if item.get("type") == "learning_image"], ["cat", "dog"])
        self.assertEqual(loader.queries, [("cat", "cat"), ("dog", "dog")])
        self.assertTrue(loader.closed)
        self.assertIn("queued", gemini.sent[0]["toolResponse"]["functionResponses"][0]["response"])

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
    async def test_missing_lesson_visual_is_shown_without_an_extra_correction_turn(self):
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
            def __init__(self): self.sent = []
            async def send(self, value): self.sent.append(json.loads(value))

        class Controller:
            def is_active(self): return False
            def is_playing(self): return False
            async def schedule_pending(self): pass

        gemini, device = Gemini(), Device()
        with patch.object(learning_image, "prepare_learning_image", return_value={
                "png": b"fallback", "verified": True, "source_title": "Apple", "source_url": "https://img"}):
            await bridge.gemini_output(
                gemini, device, None, None, "session", 1,
                {"gemini_content_seen": False}, bridge.new_speech_state(), one_turn=True,
                music_controller=Controller(),
            )
        corrections = [message for message in gemini.sent if "clientContent" in message]
        self.assertEqual(corrections, [], 'Prepare the spoken topic without another model reply')
        visuals = [message for message in device.sent
                   if message.get("type") == "learning_image"]
        self.assertEqual(len(visuals), 1)
        self.assertEqual(visuals[0]["word"], "apple")

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

    @unittest.skip('Lesson picture delivery removed from live conversations on 18/10/2026; see test_voice_only')
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
                          return_value={"png": png, "verified": True, "source_title": "Apple", "source_url": "https://img"}):
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
        self.assertIn("ask one question, then wait", prompt)
        self.assertIn("Never call music or volume tools without a new explicit user request", prompt)


if __name__ == "__main__":
    unittest.main()
