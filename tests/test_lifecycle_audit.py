import unittest
import os, stat
import test_engine as fixtures
m=fixtures.m

class LifecycleAudit(unittest.TestCase):
 setUp=fixtures.PolicyTests.setUp
 tearDown=fixtures.PolicyTests.tearDown
 heartbeat=fixtures.PolicyTests.heartbeat
 due=fixtures.PolicyTests.due
 wake=fixtures.PolicyTests.wake
 sleeping=fixtures.PolicyTests.sleeping
 @unittest.skipUnless(os.name=='posix','POSIX file permissions required')
 def test_service_umask_does_not_hide_public_state(self):
  previous=os.umask(0o027)
  try:self.engine.tick(self.now)
  finally:os.umask(previous)
  self.assertEqual(stat.S_IMODE(self.engine.public.stat().st_mode),0o644)
  self.assertEqual(stat.S_IMODE(self.engine.ledger.stat().st_mode),0o600)
 def test_open_cancels_pending_sleep(self):
  self.engine.intent('sleep','survival',self.now)
  self.heartbeat(1);self.engine.tick(self.now)
  self.engine.intent('open','survival',self.now)
  self.heartbeat(0);self.engine.tick(self.now+1)
  self.assertEqual(self.driver.calls,[])

 def test_closed_external_start_is_stopped_when_empty(self):
  self.sleeping();self.engine.intent('close','survival',self.now)
  self.engine.tick(self.now)
  self.driver.states['survival']='active'
  self.heartbeat();self.engine.tick(self.now+1)
  self.assertEqual(self.driver.calls,[('stop','survival')])

 def test_old_wake_cannot_survive_close_and_reopen(self):
  self.sleeping();self.wake()
  self.engine.intent('close','survival',self.now)
  self.engine.intent('open','survival',self.now)
  self.engine.tick(self.now+1)
  self.assertEqual(self.driver.calls,[])

 def test_many_requests_and_worker_restarts_start_once(self):
  self.sleeping()
  for i in range(100):
   self.wake();m.Engine(self.config,self.driver).tick(self.now+i)
  self.assertEqual(self.driver.calls,[('start','survival')])

 def test_close_during_start_never_publishes_ready(self):
  self.sleeping();self.wake();self.engine.tick(self.now)
  self.engine.intent('close','survival',self.now)
  self.driver.states['survival']='active';self.heartbeat(1)
  self.engine.tick(self.now+1)
  self.assertTrue(m.read_json(self.engine.public)['modes']['survival']['closed'])
  self.assertNotIn(('stop','survival'),self.driver.calls)
  self.heartbeat(0);self.engine.tick(self.now+2)
  self.assertEqual(self.driver.calls,[('start','survival'),('stop','survival')])
