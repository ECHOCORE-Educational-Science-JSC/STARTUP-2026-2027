"""Voice teaching must not search, wait for, or transmit lesson pictures."""
import base64
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bridge
from test_image_audio import PassThroughCodec, InactiveMusic


class ConversationStateTest(unittest.TestCase):
    def test_fragmented_clarification_waits_for_a_genuine_user_answer(self):
        state = bridge.learning_session.ConversationState()
        state.observe_user('Dạy bé tiếng Anh')
        state.observe_assistant('Wisio chưa nghe')
        state.observe_assistant('rõ, bé nhắc lại nhé?')
        self.assertTrue(state.waiting_for_clarification)
        state.finish_turn()
        self.assertFalse(state.begin_proactive_turn())
        state.observe_user('Học tiếng Anh về trường học')
        self.assertFalse(state.waiting_for_clarification)
        self.assertTrue(state.active)
        state.observe_user('dừng học')
        self.assertFalse(state.active)

    def test_lesson_repeat_is_not_a_request_to_clarify_hearing(self):
        state = bridge.learning_session.ConversationState()
        state.observe_assistant("The lion is big. Can you say, 'The lion is big'?")
        self.assertFalse(state.waiting_for_clarification)
        self.assertTrue(state.begin_proactive_turn())


class VoiceOnlyContractTest(unittest.TestCase):
    def test_live_setup_exposes_only_conversation_music_and_memory_tools(self):
        for model in ('gemini-3.8-live', 'gemini-3.1-flash-live-preview'):
            names = {d['name'] for t in bridge.live_tools_for_model(model)
                     for d in t['functionDeclarations']}
            self.assertFalse(names & {'show_learning_image', 'prefetch_learning_images'})
            self.assertTrue({'play_song', 'stop_music', 'adjust_volume', 'remember_user_fact',
                             'remember_learning_progress', 'recall_user_memories',
                             'forget_user_memory', 'request_clarification'} <= names)

    def test_greeting_and_active_prompt_do_not_advertise_illustrations(self):
        self.assertNotIn('hình ảnh', bridge.CONNECTION_GREETING_TEXT)
        prompt = bridge.SYSTEM_INSTRUCTION + bridge.product_prompt_context()
        for command in ('show_learning_image', 'prefetch_learning_images'):
            self.assertNotIn(command, prompt)
        self.assertIn('VOICE-ONLY', prompt)
        self.assertIn('Do not invent grammar rules', prompt)


class VoiceOnlyFlowTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def volume_tool(action='up', **args):
        return {'toolCall': {'functionCalls': [{'id': 'volume', 'name': 'adjust_volume',
                                                'args': {'action': action, **args}}]}}

    async def test_volume_confirmation_is_audio_only_after_command(self):
        pcm = bytes(range(256)) * 45
        for action, args, phrase in [
                ('up', {}, 'Mình tăng âm lượng rồi nhé!'),
                ('down', {}, 'Mình giảm âm lượng rồi nhé!'),
                ('set', {'value': 65}, 'Mình chỉnh âm lượng về 65% rồi nhé!')]:
            with self.subTest(action=action):
                packets, replies = await self.run_events([
                    self.volume_tool(action, **args),
                    {'serverContent': {'outputTranscription': {'text': phrase},
                        'modelTurn': {'parts': [{'inlineData': {
                            'data': base64.b64encode(pcm).decode()}}]}}},
                    {'serverContent': {'turnComplete': True}}])
                self.assertEqual(packets[0]['type'], 'volume')
                self.assertEqual(packets[0]['action'], action)
                self.assertEqual(b''.join(x for x in packets if isinstance(x, bytes)), pcm)
                self.assertFalse(any(isinstance(x, dict) and x.get('state') == 'sentence_start'
                                     for x in packets))
                result = replies[0]['toolResponse']['functionResponses'][0]['response']['result']
                self.assertIn(phrase, result)
                self.assertFalse(any('clientContent' in x for x in replies))

    async def test_silent_volume_reply_gets_one_speech_retry_without_second_step(self):
        packets, replies = await self.run_events([
            self.volume_tool(), {'serverContent': {'turnComplete': True}},
            self.volume_tool(),  # A model must not turn the retry into another volume increase.
            {'serverContent': {'turnComplete': True}},
            {'serverContent': {'turnComplete': True}}])
        commands = [x for x in packets if isinstance(x, dict) and x.get('type') == 'volume']
        self.assertEqual(len(commands), 1)
        corrections = [x for x in replies if 'clientContent' in x]
        self.assertEqual(len(corrections), 1)
        self.assertIn('Do not call any tool', corrections[0]['clientContent']['turns'][0]['parts'][0]['text'])

    async def test_new_user_input_cancels_old_volume_confirmation(self):
        packets, replies = await self.run_events([
            self.volume_tool(),
            {'_start_user_turn': True,
             'serverContent': {'inputTranscription': {'text': 'Dạy bé từ lion'}}},
            {'serverContent': {'turnComplete': True}}])
        self.assertFalse(any('clientContent' in x for x in replies))

    async def test_invalid_volume_action_has_no_success_confirmation(self):
        packets, replies = await self.run_events([
            self.volume_tool('invalid'), {'serverContent': {'turnComplete': True}}])
        self.assertFalse(any(isinstance(x, dict) and x.get('type') == 'volume' for x in packets))
        self.assertIn('error', replies[0]['toolResponse']['functionResponses'][0]['response'])
        self.assertFalse(any('clientContent' in x for x in replies))

    async def test_muting_does_not_request_inaudible_confirmation(self):
        for action, args in [('mute', {}), ('set', {'value': 0})]:
            packets, replies = await self.run_events([
                self.volume_tool(action, **args), {'serverContent': {'turnComplete': True}}])
            self.assertFalse(any('clientContent' in x for x in replies))
            self.assertIn('muted', replies[0]['toolResponse']['functionResponses'][0]['response']['result'])

    async def test_bad_volume_level_does_not_disconnect_or_claim_success(self):
        for value in (None, 'louder', [], {}, True, 12.5, 'nan', 'inf', 10**400):
            with self.subTest(value=repr(value)):
                packets, replies = await self.run_events([
                    self.volume_tool('set', value=value),
                    {'toolCall': {'functionCalls': [{'id': 'time', 'name': 'get_vietnam_time', 'args': {}}]}},
                    {'serverContent': {'turnComplete': True}}])
                self.assertFalse(any(isinstance(x, dict) and x.get('type') == 'volume' for x in packets))
                self.assertIn('error', replies[0]['toolResponse']['functionResponses'][0]['response'])
                self.assertIn('result', replies[1]['toolResponse']['functionResponses'][0]['response'])

    async def run_events(self, events, controller=None, memory=None, stats=None):
        packets, replies = [], []
        state = stats if stats is not None else {'gemini_content_seen': False, 'output_frames': 0}
        class Gemini:
            def __aiter__(self):
                async def source():
                    for event in events:
                        if event.pop('_start_user_turn', False):
                            state['input_turns'] = state.get('input_turns', 0) + 1
                            state['cancel_previous_visual_on_speech']()
                        yield json.dumps(event)
                return source()
            async def send(self, data): replies.append(json.loads(data))
        class Device:
            async def send(self, data):
                packets.append(json.loads(data) if isinstance(data, str) else data)
        with patch.object(bridge.learning_image, 'prepare_learning_image',
                          side_effect=AssertionError('Lesson image I/O is disabled')) as search, \
             patch.object(bridge.learning_session, 'LearningVisualState',
                          side_effect=AssertionError('No visual topic parsing in voice conversation')):
            await bridge.gemini_output(
                Gemini(), Device(), None, PassThroughCodec(), 's', 1,
                state,
                bridge.new_speech_state(), music_controller=controller or InactiveMusic(),
                memory_store=memory)
            search.assert_not_called()
        return packets, replies

    async def test_split_pcm_survives_stale_image_calls_and_no_correction_turn(self):
        pcm = bytes(range(256)) * 45  # Four exact Opus frames with awkward chunk boundaries.
        def audio(data):
            return {'serverContent': {'modelTurn': {'parts': [
                {'inlineData': {'data': base64.b64encode(data).decode()}}]}}}
        events = [
            {'serverContent': {'inputTranscription': {'text': 'Dạy bé về con sư tử'}}},
            audio(pcm[:1001]),
            {'toolCall': {'functionCalls': [
                {'id': 'old1', 'name': 'show_learning_image', 'args': {'word': 'lion', 'query': 'lion'}},
                {'id': 'old2', 'name': 'prefetch_learning_images', 'args': {'items': [{'word': 'lion'}]}}]}},
            {'serverContent': {'outputTranscription': {'text': 'A lion is a big cat.'}}},
            audio(pcm[1001:]), {'serverContent': {'turnComplete': True}}]
        packets, replies = await self.run_events(events)
        self.assertEqual(b''.join(x for x in packets if isinstance(x, bytes)), pcm)
        self.assertEqual([x['state'] for x in packets if isinstance(x, dict) and
                          x.get('type') == 'tts' and x.get('state') in ('start', 'stop')], ['start', 'stop'])
        self.assertFalse(any(x.get('type') == 'learning_image' for x in packets if isinstance(x, dict)))
        self.assertFalse(any('clientContent' in x for x in replies))
        results = [r['response'] for x in replies
                   for r in x.get('toolResponse', {}).get('functionResponses', [])]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['disabled'] and not r['retry_allowed'] for r in results))

    async def test_silent_completion_does_not_request_an_image_or_extra_model_turn(self):
        packets, replies = await self.run_events([
            {'serverContent': {'inputTranscription': {'text': 'Cho xem ảnh con mèo màu cam'}}},
            {'serverContent': {'turnComplete': True}}])
        self.assertFalse(replies)
        self.assertFalse(any(x.get('type') == 'learning_image' for x in packets))

    async def test_confirmed_memory_is_still_saved_without_a_visual_turn(self):
        memory = MagicMock()
        memory.remember.return_value = {'saved': True}
        packets, replies = await self.run_events([
            {'serverContent': {'inputTranscription': {'text': 'Bé tên Bo, bé thích khủng long'}}},
            {'toolCall': {'functionCalls': [{'id': 'save', 'name': 'remember_user_fact',
                'args': {'fact': 'Bé Bo thích khủng long.'}}]}},
            {'serverContent': {'turnComplete': True}}], memory=memory)
        memory.remember.assert_called_once_with('Bé Bo thích khủng long.')
        self.assertTrue(replies[0]['toolResponse']['functionResponses'][0]['response']['result']['saved'])

    async def test_followup_context_keeps_all_fragments_of_the_current_question(self):
        stats = {'gemini_content_seen': False, 'output_frames': 0}
        await self.run_events([
            {'serverContent': {'inputTranscription': {'text': 'Bé muốn học tiếng Anh'}}},
            {'serverContent': {'inputTranscription': {'text': 'về trường học'}}},
            {'serverContent': {'turnComplete': True}}], stats=stats)
        self.assertEqual(stats['last_input_text'], 'Bé muốn học tiếng Anh về trường học')


if __name__ == '__main__':
    unittest.main()
