"""Music artwork/start ownership tests with local audio and image fixtures."""

import asyncio
import base64
import io
import json
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

import bridge
import music


def image_bytes(color):
    buffer = io.BytesIO()
    Image.new('RGB', (480, 360), color).save(buffer, 'PNG')
    return buffer.getvalue()


class Device:
    def __init__(self):
        self.sent = []
        self.ready_at_audio_send = []
        self.controller = None
        self.music_start_at = None

    async def send(self, value):
        if isinstance(value, bytes):
            self.ready_at_audio_send.append(self.controller.playback_ready.is_set())
        elif json.loads(value).get('state') == 'start':
            self.music_start_at = time.monotonic()
        self.sent.append(value)


class Codec:
    def encode(self, _encoder, _pcm):
        return b'opus'


class AtomicMusicStartTest(unittest.IsolatedAsyncioTestCase):
    def controller(self):
        device = Device()
        controller = bridge.MusicController(device, None, Codec(), 'session', 1,
                                            {'output_frames': 0})
        device.controller = controller
        return controller, device

    def events(self, device):
        return [json.loads(value) for value in device.sent if isinstance(value, str)]

    async def short_frames(self, _track, frame_bytes):
        yield bytes(frame_bytes)
        yield bytes(frame_bytes)

    async def finish(self, controller):
        if controller.task is not None:
            await asyncio.wait_for(controller.task, 2)

    def assert_cover(self, event, color):
        self.assertIn('mime_type', event, 'Start must carry the prepared cover with metadata')
        self.assertIn('data', event, 'Start must carry the prepared cover with metadata')
        self.assertEqual(event['mime_type'], 'image/png')
        with Image.open(io.BytesIO(base64.b64decode(event['data']))) as cover:
            self.assertEqual(cover.size, (320, 240))
            self.assertEqual(cover.getpixel((160, 120)), color)
        self.assertRegex(event['accent_color'], r'^#[0-9A-Fa-f]{6}$')

    async def test_cover_prepares_while_first_pcm_waits_then_start_is_complete(self):
        controller, device = self.controller()
        track = music.Track('one', 'Blue Sky', 'Luna', thumbnail_url='https://img/one',
                            duration=12.5, display_title='Bầu Trời Xanh')
        cover_read, pcm_release = threading.Event(), asyncio.Event()
        def read(*_args):
            cover_read.set()
            return image_bytes((20, 160, 240))
        async def frames(_track, frame_bytes):
            await pcm_release.wait()
            yield bytes(frame_bytes)
            yield bytes(frame_bytes)
        with patch.object(bridge, 'music_setup_problem', return_value=None), \
             patch.object(music, 'search_track', return_value=track), \
             patch.object(music, 'pcm_frames', side_effect=frames), \
             patch.object(bridge.learning_image, '_read_url', side_effect=read):
            preparation = asyncio.create_task(controller.prepare('Blue Sky'))
            try:
                self.assertTrue(await asyncio.to_thread(cover_read.wait, 0.5),
                                'Artwork should load concurrently with first PCM')
            finally:
                pcm_release.set()
            await preparation
            self.assertEqual(device.sent, [], 'Preparing must not show or start music early')
            await controller.start_pending()
            await self.finish(controller)
        start = self.events(device)[0]
        self.assertEqual((start['state'], start['title'], start['artist'], start['duration_ms']),
                         ('start', 'Bầu Trời Xanh', 'Luna', 12500))
        self.assert_cover(start, (20, 160, 240))
        self.assertFalse(device.ready_at_audio_send[0])
        self.assertTrue(controller.playback_ready.is_set())
        self.assertFalse(any(event['state'] == 'cover' for event in self.events(device)))

    async def test_fast_cover_on_direct_pending_is_in_start_event(self):
        controller, device = self.controller()
        controller.pending = music.Track('one', 'Song', 'Artist', thumbnail_url='https://img/one')
        with patch.object(music, 'pcm_frames', side_effect=self.short_frames), \
             patch.object(bridge.learning_image, '_read_url', return_value=image_bytes((200, 50, 80))):
            await controller.start_pending()
            await self.finish(controller)
        self.assert_cover(self.events(device)[0], (200, 50, 80))

    async def test_slow_cover_does_not_delay_start_or_change_screen_later(self):
        controller, device = self.controller()
        controller.pending = music.Track('slow', 'Song', 'Artist', thumbnail_url='https://img/slow')
        read_started, release = threading.Event(), threading.Event()
        playback_release = asyncio.Event()
        def read(*_args):
            read_started.set()
            release.wait(2)
            return image_bytes((255, 0, 0))
        async def frames(_track, frame_bytes):
            yield bytes(frame_bytes)
            await playback_release.wait()
            yield bytes(frame_bytes)
        with patch.object(music, 'pcm_frames', side_effect=frames), \
             patch.object(bridge.learning_image, '_read_url', side_effect=read):
            try:
                started_at = time.monotonic()
                # Audio also waits for its normal playback lead; artwork itself
                # must finish or fall back before that existing buffer delay.
                await asyncio.wait_for(controller.start_pending(), 1.3)
                self.assertLess(device.music_start_at - started_at, 0.5)
                self.assertTrue(read_started.is_set())
                count_before_art_finishes = len(device.sent)
                release.set()
                await asyncio.sleep(0.05)
                self.assertEqual(len(device.sent), count_before_art_finishes)
                playback_release.set()
                await self.finish(controller)
            finally:
                release.set()
                playback_release.set()
                await controller.stop()
        start = self.events(device)[0]
        self.assertEqual(start['state'], 'start')
        self.assertNotIn('data', start, 'Firmware must use its complete music placeholder')
        self.assertFalse(any(event['state'] == 'cover' for event in self.events(device)))

    async def test_failed_cover_uses_start_placeholder_and_still_delivers_audio(self):
        controller, device = self.controller()
        controller.pending = music.Track('failed', 'Song', 'Artist', thumbnail_url='https://img/fail')
        with patch.object(music, 'pcm_frames', side_effect=self.short_frames), \
             patch.object(bridge.learning_image, '_read_url', side_effect=OSError('offline')):
            await controller.start_pending()
            await self.finish(controller)
        self.assertNotIn('data', self.events(device)[0])
        self.assertEqual(sum(value == b'opus' for value in device.sent), 2)

    async def test_missing_cover_never_requests_network_and_starts_placeholder(self):
        controller, device = self.controller()
        controller.pending = music.Track('plain', 'Song', 'Artist')
        with patch.object(music, 'pcm_frames', side_effect=self.short_frames), \
             patch.object(bridge.learning_image, '_read_url') as read:
            await controller.start_pending()
            await self.finish(controller)
        read.assert_not_called()
        self.assertNotIn('data', self.events(device)[0])

    async def test_replaced_track_never_sends_old_cover(self):
        controller, device = self.controller()
        old = music.Track('old', 'Old Song', 'Artist', thumbnail_url='https://img/old')
        new = music.Track('new', 'New Song', 'Artist', thumbnail_url='https://img/new')
        old_started, old_release = threading.Event(), threading.Event()
        def read(url, *_args):
            if url.endswith('old'):
                old_started.set()
                old_release.wait(2)
                return image_bytes((255, 0, 0))
            return image_bytes((0, 0, 255))
        with patch.object(bridge, 'music_setup_problem', return_value=None), \
             patch.object(music, 'search_track', side_effect=[old, new]), \
             patch.object(music, 'pcm_frames', side_effect=self.short_frames), \
             patch.object(bridge.learning_image, '_read_url', side_effect=read):
            try:
                await controller.prepare('old')
                self.assertTrue(await asyncio.to_thread(old_started.wait, 0.5))
                await controller.prepare('new')
                await controller.start_pending()
                await self.finish(controller)
                old_release.set()
                await asyncio.sleep(0.05)
            finally:
                old_release.set()
                await controller.stop()
        starts = [event for event in self.events(device) if event['state'] == 'start']
        self.assertEqual([event['title'] for event in starts], ['New Song'])
        self.assert_cover(starts[0], (0, 0, 255))

    async def test_cancelled_prepare_closes_pcm_and_discards_cover_without_screen_events(self):
        controller, device = self.controller()
        track = music.Track('old', 'Old Song', 'Artist', thumbnail_url='https://img/old')
        first_pcm_waiting, stream_closed = asyncio.Event(), asyncio.Event()
        cover_read, cover_release = threading.Event(), threading.Event()
        def read(*_args):
            cover_read.set()
            cover_release.wait(2)
            return image_bytes((255, 0, 0))
        async def frames(_track, frame_bytes):
            try:
                first_pcm_waiting.set()
                await asyncio.Event().wait()
                yield bytes(frame_bytes)
            finally:
                stream_closed.set()
        with patch.object(bridge, 'music_setup_problem', return_value=None), \
             patch.object(music, 'search_track', return_value=track), \
             patch.object(music, 'pcm_frames', side_effect=frames), \
             patch.object(bridge.learning_image, '_read_url', side_effect=read):
            try:
                preparation = asyncio.create_task(controller.prepare('old'))
                await asyncio.wait_for(first_pcm_waiting.wait(), 1)
                self.assertTrue(await asyncio.to_thread(cover_read.wait, 0.5))
                preparation.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await preparation
                self.assertTrue(stream_closed.is_set())
                self.assertIsNone(controller.cover_task)
                self.assertIsNone(controller.prepared_stream)
                self.assertFalse(controller.is_active())
                cover_release.set()
                await asyncio.sleep(0.05)
            finally:
                cover_release.set()
                await controller.stop()
        self.assertEqual(device.sent, [])

    async def test_reassert_preserves_position_without_resending_artwork(self):
        controller, device = self.controller()
        controller.pending = music.Track('one', 'Song', 'Artist', thumbnail_url='https://img/one')
        release = asyncio.Event()
        async def frames(_track, frame_bytes):
            yield bytes(frame_bytes)
            await release.wait()
        with patch.object(music, 'pcm_frames', side_effect=frames), \
             patch.object(bridge.learning_image, '_read_url', return_value=image_bytes((200, 50, 80))) as read:
            try:
                await controller.start_pending()
                controller.position_ms = 4200
                await controller.reassert_playing()
            finally:
                release.set()
                await self.finish(controller)
        starts = [event for event in self.events(device) if event['state'] == 'start']
        self.assertEqual(len(starts), 2)
        self.assertIn('data', starts[0], 'The initial start must still carry the prepared cover')
        self.assertNotIn('data', starts[1], 'An active screen should not decode the same cover again')
        self.assertEqual(starts[1]['position_ms'], 4200)
        self.assertEqual(starts[0]['playback_token'], starts[1]['playback_token'])
        read.assert_called_once()

    async def test_reassert_during_cover_preparation_cannot_publish_placeholder_first(self):
        controller, device = self.controller()
        controller.pending = music.Track('one', 'Song', 'Artist', thumbnail_url='https://img/one')
        preparing, release = asyncio.Event(), asyncio.Event()
        async def cover(_track):
            preparing.set()
            await release.wait()
            return {'mime_type': 'image/png', 'accent_color': '#145AF0',
                    'data': base64.b64encode(image_bytes((20, 90, 240))).decode('ascii')}
        with patch.object(music, 'pcm_frames', side_effect=self.short_frames), \
             patch.object(controller, '_prepare_cover_art', side_effect=cover):
            start = asyncio.create_task(controller.start_pending())
            try:
                await asyncio.wait_for(preparing.wait(), 1)
                await controller.reassert_playing()
                self.assertEqual(self.events(device), [],
                                 'A late listen must wait for the initial complete screen')
            finally:
                release.set()
                await start
                await self.finish(controller)
        starts = [event for event in self.events(device) if event['state'] == 'start']
        self.assertEqual(len(starts), 1)
        self.assertIn('data', starts[0])


if __name__ == '__main__':
    unittest.main()
