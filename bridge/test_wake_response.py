"""Wake is a control event, with a bounded spoken acknowledgement and microphone recovery."""
import asyncio
import base64
import json
import unittest
import os
import threading
import websockets
from unittest.mock import patch

import bridge
import test_voice_only as voice_tests


class WakeResponseTest(unittest.IsolatedAsyncioTestCase):
    class Peer:
        def __init__(self): self.sent = []
        async def send(self, value): self.sent.append(json.loads(value))

    class Music:
        def __init__(self, active=False): self.active = active
        def is_active(self): return self.active

    async def test_wake_requests_exactly_one_short_ack_without_recorded_audio(self):
        peer, stats = self.Peer(), {}
        speech = bridge.new_speech_state()
        self.assertTrue(await bridge.acknowledge_wake(peer, speech, stats, self.Music()))
        prompt = peer.sent[0]['clientContent']['turns'][0]['parts'][0]['text']
        self.assertIn(bridge.WAKE_ACK_TEXT, prompt)
        self.assertIn('Do not call tools', prompt)
        self.assertTrue(stats['greeting_pending'])
        self.assertFalse(speech['started'])
        self.assertFalse(await bridge.acknowledge_wake(peer, speech, stats, self.Music()))
        self.assertEqual(len(peer.sent), 1)

    async def test_wake_does_not_interrupt_music_intro_child_or_an_answer(self):
        for stats, speaking, music in [
                ({'greeting_pending': True}, False, False),
                ({'assistant_response_pending': True}, False, False),
                ({'assistant_speaking': True}, False, False),
                ({}, True, False), ({}, False, True)]:
            peer = self.Peer()
            speech = bridge.new_speech_state()
            speech['started'] = speaking
            self.assertFalse(await bridge.acknowledge_wake(peer, speech, stats, self.Music(music)))
            self.assertEqual(peer.sent, [])

    async def test_duplicate_wake_has_a_short_debounce_then_allows_another_call(self):
        peer, stats, speech = self.Peer(), {}, bridge.new_speech_state()
        self.assertTrue(await bridge.acknowledge_wake(peer, speech, stats, self.Music()))
        stats.update(greeting_pending=False, assistant_response_pending=False)
        self.assertFalse(await bridge.acknowledge_wake(peer, speech, stats, self.Music()))
        stats['last_wake_ack_at'] -= 3
        self.assertTrue(await bridge.acknowledge_wake(peer, speech, stats, self.Music()))
        self.assertEqual(len(peer.sent), 2)

    async def test_failed_wake_prompt_does_not_leave_microphone_guard_stuck(self):
        class Failed:
            async def send(self, _): raise ConnectionError('closed')
        stats = {}
        with self.assertRaises(ConnectionError):
            await bridge.acknowledge_wake(Failed(), bridge.new_speech_state(), stats, self.Music())
        self.assertFalse(stats['greeting_pending'])
        self.assertFalse(stats['assistant_response_pending'])

    async def test_ack_audio_uses_the_real_playback_then_clears_the_greeting_guard(self):
        peer, stats = self.Peer(), {'gemini_content_seen': False, 'output_frames': 0}
        await bridge.acknowledge_wake(peer, bridge.new_speech_state(), stats, self.Music())
        pcm = bytes(range(256)) * 45
        packets, _ = await voice_tests.VoiceOnlyFlowTest.run_events(self, [
            {'serverContent': {'modelTurn': {'parts': [{'inlineData': {
                'data': base64.b64encode(pcm).decode()}}]}}},
            {'serverContent': {'turnComplete': True}}], stats=stats)
        tts = [x['state'] for x in packets if isinstance(x, dict) and x.get('type') == 'tts']
        self.assertEqual(tts, ['start', 'stop'])
        self.assertEqual(b''.join(x for x in packets if isinstance(x, bytes)), pcm)
        self.assertFalse(stats['greeting_pending'])
        self.assertFalse(stats['assistant_response_pending'])

    async def test_silent_ack_timeout_reopens_listening_and_allows_future_wakes(self):
        peer, stats = self.Peer(), {'greeting_pending': True, 'assistant_response_pending': True}
        with patch.object(bridge, 'CONNECTION_GREETING_WAIT_SECONDS', 0):
            await bridge.resume_after_greeting_wait(peer, 's', stats)
        self.assertFalse(stats['greeting_pending'])
        self.assertFalse(stats['assistant_response_pending'])
        self.assertEqual(peer.sent, [{'type': 'listen', 'state': 'start', 'session_id': 's'}])

    async def test_previous_intro_timer_cannot_release_a_new_wake_ack(self):
        peer, stats = self.Peer(), {'greeting_pending': True}
        async def new_ack(_):
            stats['greeting_generation'] = 1
        with patch.object(bridge.asyncio, 'sleep', side_effect=new_ack):
            await bridge.resume_after_greeting_wait(peer, 's', stats)
        self.assertTrue(stats['greeting_pending'])
        self.assertEqual(peer.sent, [])

    async def test_actual_device_route_turns_a_wake_event_into_speaker_packets(self):
        codec = bridge.Opus(bridge.find_opus_library())
        prompts = []
        settings_threads=[]
        main_thread=threading.get_ident()
        real_alerter=bridge.guardian_alert.GuardianAlerter
        def load_alerter(recipient):
            settings_threads.append(threading.get_ident())
            return real_alerter(recipient)
        async def model(ws):
            await ws.recv()  # setup; no real API is contacted
            await bridge.send_json(ws, {'setupComplete': {}})
            async for raw in ws:
                event = json.loads(raw)
                if 'clientContent' not in event:
                    continue
                prompts.append(event['clientContent']['turns'][0]['parts'][0]['text'])
                await bridge.send_json(ws, {'serverContent': {
                    'modelTurn': {'parts': [{'inlineData': {'data': base64.b64encode(
                        bytes(bridge.OUTPUT_SAMPLES * 4)).decode()}}]},
                    'turnComplete': True}})
        async with websockets.serve(model, '127.0.0.1', 0) as model_server:
            model_port = model_server.sockets[0].getsockname()[1]
            with patch.object(bridge, 'GEMINI_ENDPOINT', f'ws://127.0.0.1:{model_port}/model'), \
                 patch.dict(os.environ, {'WISIO_DIAGNOSTIC': '0'}), \
                 patch.object(bridge.guardian_alert, 'GuardianAlerter', side_effect=load_alerter):
                async with websockets.serve(
                        lambda ws: bridge.handle_device(ws, 'fake-key', codec), '127.0.0.1', 0) as robot_server:
                    robot_port = robot_server.sockets[0].getsockname()[1]
                    async with websockets.connect(f'ws://127.0.0.1:{robot_port}/wisio/v1/') as robot:
                        await bridge.send_json(robot, {'type': 'hello', 'transport': 'websocket', 'version': 1})
                        hello = json.loads(await asyncio.wait_for(robot.recv(), 5))
                        self.assertFalse(hello['greeting_pending'])
                        await bridge.send_json(robot, {'type': 'listen', 'state': 'detect', 'text': 'Hey Wisio'})
                        states, audio_packets = [], []
                        async with asyncio.timeout(8):
                            while not states or states[-1] != 'stop':
                                frame = await robot.recv()
                                if isinstance(frame, bytes):
                                    audio_packets.append(frame)
                                else:
                                    event = json.loads(frame)
                                    if event.get('type') == 'tts': states.append(event['state'])
                        self.assertEqual(states, ['start', 'stop'])
                        self.assertTrue(audio_packets)
                        self.assertEqual(len(prompts), 1)
                        self.assertIn(bridge.WAKE_ACK_TEXT, prompts[0])
                        self.assertTrue(settings_threads)
                        self.assertNotEqual(settings_threads[0],main_thread)


if __name__ == '__main__':
    unittest.main()
