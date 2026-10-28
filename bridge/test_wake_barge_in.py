"""Wake cancels queued speech and waits for the old model generation to end."""
import asyncio
import base64
import json
import unittest
import bridge
from test_voice_only import PassThroughCodec, InactiveMusic

class BargeInTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, draining):
        class Gemini:
            def __init__(self): self.queue=asyncio.Queue(); self.sent=[]
            def __aiter__(self):
                async def stream():
                    while True:
                        value=await self.queue.get()
                        if value is None: return
                        yield json.dumps(value)
                return stream()
            async def send(self, raw): self.sent.append(json.loads(raw))
        class Device:
            def __init__(self): self.sent=[]
            async def send(self, raw): self.sent.append(json.loads(raw) if isinstance(raw,str) else raw)
        async def wait(predicate):
            async with asyncio.timeout(4):
                while not predicate(): await asyncio.sleep(.005)
        def audio(pcm):
            return {'serverContent': {'modelTurn': {'parts': [{'inlineData': {
                'data': base64.b64encode(pcm).decode()}}]}}}
        gemini,device=Gemini(),Device()
        stats={'gemini_content_seen':False,'output_frames':0}
        task=asyncio.create_task(bridge.gemini_output(gemini,device,None,
            PassThroughCodec(),'s',1,stats,bridge.new_speech_state(),music_controller=InactiveMusic()))
        try:
            await gemini.queue.put(audio(b'\x01\x02'*bridge.OUTPUT_SAMPLES*8))
            await wait(lambda: any(isinstance(x,bytes) for x in device.sent))
            if draining:
                await gemini.queue.put({'serverContent':{'turnComplete':True}})
                await asyncio.sleep(.02)
            await stats['interrupt_for_wake']()
            await stats['interrupt_for_wake']()
            after_interrupt=len(device.sent)
            if not draining:
                await gemini.queue.put(audio(b'\x33\x44'*bridge.OUTPUT_SAMPLES))
                await gemini.queue.put({'toolCall':{'functionCalls':[{
                    'id':'stale','name':'adjust_volume','args':{'action':'up'}}]}})
                await gemini.queue.put({'serverContent':{'interrupted':True}})
            await wait(lambda: any('clientContent' in x for x in gemini.sent))
            controls=[x for x in gemini.sent if 'realtimeInput' in x]
            self.assertEqual(controls,[{'realtimeInput':{'activityStart':{}}},
                                       {'realtimeInput':{'activityEnd':{}}}])
            self.assertIn(bridge.WAKE_ACK_TEXT,str(gemini.sent[-1]))
            self.assertFalse(any(isinstance(x,bytes) for x in device.sent[after_interrupt:]))
            self.assertFalse(any(isinstance(x,dict) and x.get('type')=='volume' for x in device.sent))
            ack=b'\x55\x66'*bridge.OUTPUT_SAMPLES*2
            await gemini.queue.put(audio(ack))
            await gemini.queue.put({'serverContent':{'turnComplete':True}})
            await wait(lambda: not stats.get('assistant_response_pending'))
            await gemini.queue.put(None)
            await asyncio.wait_for(task,4)
            self.assertIn(ack,b''.join(x for x in device.sent[after_interrupt:] if isinstance(x,bytes)))
            self.assertFalse(stats.get('greeting_pending'))
            self.assertNotIn('interrupt_for_wake',stats)
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
    async def test_wake_during_stream_discards_old_pcm_and_tools(self): await self.exercise(False)
    async def test_wake_during_finish_keeps_receiver_and_new_ack(self): await self.exercise(True)

    async def test_real_websocket_wake_interrupts_intro_and_gets_new_speaker_packets(self):
        import os
        import websockets
        from unittest.mock import patch
        codec=bridge.Opus(bridge.find_opus_library())
        prompts=[];activities=[]
        async def model(ws):
            setup=json.loads(await ws.recv())
            self.assertEqual(setup['setup']['realtimeInputConfig']['activityHandling'],
                             'START_OF_ACTIVITY_INTERRUPTS')
            await bridge.send_json(ws,{'setupComplete':{}})
            async for raw in ws:
                event=json.loads(raw)
                if 'realtimeInput' in event:
                    activities.append(event['realtimeInput'])
                    if 'activityStart' in event['realtimeInput']:
                        await bridge.send_json(ws,{'serverContent':{'interrupted':True}})
                if 'clientContent' not in event: continue
                prompts.append(str(event))
                count=30 if len(prompts)==1 else 2
                await bridge.send_json(ws,{'serverContent':{'modelTurn':{'parts':[{'inlineData':{
                    'data':base64.b64encode(bytes(bridge.OUTPUT_SAMPLES*2*count)).decode()}}]}}})
                if len(prompts)>1:
                    await bridge.send_json(ws,{'serverContent':{'turnComplete':True}})
        async with websockets.serve(model,'127.0.0.1',0) as model_server:
            port=model_server.sockets[0].getsockname()[1]
            with patch.object(bridge,'GEMINI_ENDPOINT',f'ws://127.0.0.1:{port}/model'), \
                 patch.dict(os.environ,{'WISIO_DIAGNOSTIC':'0'}):
                async with websockets.serve(lambda ws:bridge.handle_device(ws,'fake-key',codec),
                                             '127.0.0.1',0) as server:
                    robot_port=server.sockets[0].getsockname()[1]
                    async with websockets.connect(f'ws://127.0.0.1:{robot_port}/wisio/v1/') as robot:
                        await bridge.send_json(robot,{'type':'hello','transport':'websocket',
                                                      'version':1,'wisio_id':'test'})
                        self.assertTrue(json.loads(await robot.recv())['greeting_pending'])
                        async with asyncio.timeout(8):
                            while True:
                                frame=await robot.recv()
                                if isinstance(frame,bytes): break
                            await bridge.send_json(robot,{'type':'abort','reason':'wake_word_detected'})
                            await bridge.send_json(robot,{'type':'listen','state':'detect','text':'Hey Wisio'})
                            states=[];packets=0
                            while not states or states[-1]!='stop' or 'start' not in states:
                                frame=await robot.recv()
                                if isinstance(frame,bytes):packets+=1
                                else:
                                    event=json.loads(frame)
                                    if event.get('type')=='tts':states.append(event['state'])
                        self.assertEqual(len(prompts),2)
                        self.assertIn(bridge.WAKE_ACK_TEXT,prompts[1])
                        self.assertEqual(activities,[{'activityStart':{}},{'activityEnd':{}}])
                        self.assertGreater(packets,0)

if __name__=='__main__':unittest.main()
