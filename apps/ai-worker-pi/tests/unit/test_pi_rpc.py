"""Exercise real subprocess pipes against a deterministic Pi protocol peer."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.pi_runtime.client import _CHILDREN, Pi, check_runtime

PEER = r"""#!/usr/bin/env python3
import json,sys,time,os
from pathlib import Path
if '--version' in sys.argv:
 print('1.3.0');sys.exit()
Path('pid').write_text(str(os.getpid()))
line=sys.stdin.buffer.readline()
r=json.loads(line)
m=r['message']
def emit(x):
 print(json.dumps(x),flush=True)
if m=='crash':sys.exit(2)
if m=='invalid':print('not json',flush=True);time.sleep(60)
if m=='timeout':time.sleep(60)
if m=='reject':
 emit({'type':'response','id':r['id'],'success':False,'error':'SECRET'});time.sleep(60)
response={'type':'response','id':r['id'],'success':True,'data':{'disposition':'handled' if m=='handled' else 'started'}}
if m!='fast':emit(response)
if m=='handled':time.sleep(60)
session=Path(sys.argv[sys.argv.index('--session')+1])
history=json.loads(session.read_text()) if session.exists() else []
history.append(m);session.write_text(json.dumps(history))
if m=='recover':
 emit({'type':'message_end','message':{'role':'assistant','stopReason':'error','errorMessage':'SECRET'}})
 emit({'type':'agent_end'})
content=json.dumps({'history':history,'images':r.get('images',[]),'agentDir':os.environ['PI_CODING_AGENT_DIR'],'hasKey':bool(os.environ.get('MTX_PI_API_KEY'))})
emit({'type':'message_end','message':{'role':'assistant','stopReason':m if m in ('length','error','aborted') else 'stop','content':[{'type':'text','text':content}],'usage':{'input':3,'output':2}}})
emit({'type':'agent_end'})
emit({'type':'agent_settled'})
if m=='fast':emit(response)
for _ in sys.stdin:pass
"""


class PiRpcTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        peer = self.root / "pi"
        peer.write_text(PEER)
        peer.chmod(0o755)
        self.config = {
            **PiConfig(
                executable=str(peer), runtime_root=str(self.root), stream_idle_timeout_seconds=0.3
            ).model_dump(),
            "model": "m",
            "base_url": "https://example.test/v1",
            "api_key": "secret",
        }
        self.path = self.root / "config.json"
        self.save()
        self.workspace = self.root / "work"

    def save(self):
        self.path.write_text(json.dumps(self.config))

    def client(self):
        return Pi.from_config(config_path=str(self.path), workspace=str(self.workspace))

    async def test_images_session_resume_and_temporary_configuration_cleanup(self):
        image = self.root / "image.png"
        image.write_bytes(b"image")
        async with self.client() as bot:
            first = await bot.run("hello\u2028world", session_key="run", media=[str(image)])
        data = json.loads(first.content)
        self.assertEqual(data["images"][0]["mimeType"], "image/png")
        self.assertEqual(data["images"][0]["data"], "aW1hZ2U=")
        self.assertTrue(data["hasKey"])
        self.assertFalse(Path(data["agentDir"]).exists())
        async with self.client() as bot:
            second = await bot.run("again", session_key="run")
            other = await bot.run("other", session_key="different")
        self.assertEqual(json.loads(second.content)["history"], ["hello\u2028world", "again"])
        self.assertEqual(json.loads(other.content)["history"], ["other"])
        self.assertEqual(first.usage, {"input": 3, "output": 2})

    async def test_fast_settled_before_ack_and_recovery(self):
        for message in ["fast", "recover"]:
            result = await self.client().run(message, session_key=message)
            self.assertEqual(result.finish_reason, "stop")

    async def test_truncation_cannot_be_published_as_a_complete_artifact(self):
        with self.assertRaisesRegex(RuntimeError, "length"):
            await self.client().run("length", session_key="run")

    async def test_errors_never_expose_provider_details(self):
        for message in ["error", "aborted", "reject", "handled", "invalid", "crash"]:
            with self.subTest(message=message), self.assertRaises(RuntimeError) as caught:
                await self.client().run(message, session_key=message)
            self.assertNotIn("SECRET", str(caught.exception))
        self.assertFalse(_CHILDREN)

    async def test_idle_timeout_reaps_process(self):
        with self.assertRaises(TimeoutError):
            await self.client().run("timeout", session_key="run")
        pid = int((self.workspace / "pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(_CHILDREN)

    async def test_total_deadline_and_cancellation_reap_process(self):
        self.config.update(run_timeout_seconds=0.2, stream_idle_timeout_seconds=30)
        self.save()
        with self.assertRaises(TimeoutError):
            await self.client().run("timeout", session_key="run")
        self.config["run_timeout_seconds"] = 30
        self.save()
        pending = asyncio.create_task(self.client().run("timeout", session_key="cancel"))
        await asyncio.sleep(0.1)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertFalse(_CHILDREN)

    def test_startup_version_check(self):
        check_runtime(self.config["executable"])
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            check_runtime(str(self.root / "missing"))
