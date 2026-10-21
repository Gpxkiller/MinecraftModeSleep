import contextlib, copy, importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('modesleep',Path(__file__).parents[1]/'daemon/modesleep.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Driver:
 def __init__(self): self.states={'survival':'active','arena':'active'};self.calls=[];self.busy=0;self.listeners=1;self.is_ready=True;self.gated=False;self.race=False
 def active(self, mode): return self.states[mode['id']]
 def start(self, mode): self.calls.append(('start',mode['id']));self.states[mode['id']]='activating'
 def stop(self, mode):
  assert self.gated
  self.calls.append(('stop',mode['id']));self.states[mode['id']]='inactive'
 def ready(self, mode): return self.is_ready
 def inventory(self, port): return (1 if self.race else self.busy),self.listeners
 def audit(self,*args): pass
 @contextlib.contextmanager
 def gate(self, port):
  self.gated=True
  class Gate:
   def verify(inner): assert self.gated
  try: yield Gate()
  finally: self.gated=False

class PolicyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'ipc'
  for p in ['private','public','inbox']:(self.root/p).mkdir(parents=True)
  self.config={'enabled':True,'ipcRoot':str(self.root),'idleSeconds':86400,'protectedPorts':[25565,25566],'modes':[{'id':'survival','unit':'mc-survival.service','port':25601}]}
  self.driver=Driver();self.engine=m.Engine(self.config,self.driver);self.now=2000000
  self.heartbeat();self.engine.tick(self.now)
 def tearDown(self):self.tmp.cleanup()
 def heartbeat(self,count=0,now=None):m.atomic(self.root/'inbox/heartbeat.json',{'generatedAt':self.now if now is None else now,'counts':{'survival':count}})
 def due(self):
  self.now+=86400;self.heartbeat()
 def wake(self):
  p=self.root/'inbox/survival.wake';p.write_text('wake');os.utime(p,(self.now,self.now))
 def sleeping(self):self.due();self.engine.tick(self.now);self.assertEqual(self.engine.load()['survival']['phase'],'sleeping');self.driver.calls.clear()
 def test_idle_stops_only_target(self):self.due();self.engine.tick(self.now);self.assertEqual(self.driver.calls,[('stop','survival')]);self.assertEqual(self.driver.states['arena'],'active')
 def test_before_delay_does_not_stop(self):self.now+=86399;self.heartbeat();self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_player_prevents_stop(self):self.due();self.heartbeat(1);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_invisible_physical_connection_prevents_stop(self):self.due();self.driver.busy=1;self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_connection_arriving_inside_gate_prevents_stop(self):self.due();self.driver.race=True;self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_missing_listener_prevents_stop(self):self.due();self.driver.listeners=0;self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_multiple_listeners_prevent_stop(self):self.due();self.driver.listeners=2;self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_stale_heartbeat_resets_idle_baseline(self):self.due();self.heartbeat(now=self.now-31);self.engine.tick(self.now);self.assertFalse(self.driver.calls);self.assertEqual(self.engine.load()['survival']['lastBusy'],self.now)
 def test_unknown_count_prevents_stop(self):self.due();self.heartbeat(None);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_invalid_heartbeat_shape_prevents_stop(self):self.due();m.atomic(self.root/'inbox/heartbeat.json',[]);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_boolean_count_is_not_empty(self):self.due();self.heartbeat(False);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_negative_count_prevents_stop(self):self.due();self.heartbeat(-1);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_future_heartbeat_prevents_stop(self):self.due();self.heartbeat(now=self.now+10);self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_disabled_config_never_controls_services(self):self.engine.config['enabled']=False;self.due();self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_one_wake_starts_once_for_many_players(self):
  self.sleeping();self.wake();self.engine.tick(self.now);self.engine.tick(self.now+1);self.assertEqual(self.driver.calls,[('start','survival')]);self.assertEqual(self.engine.load()['survival']['phase'],'starting')
 def test_ready_is_required_before_players_can_transfer(self):
  self.sleeping();self.wake();self.engine.tick(self.now);self.driver.states['survival']='active';self.driver.is_ready=False;self.engine.tick(self.now+1);self.assertEqual(self.engine.load()['survival']['phase'],'starting');self.driver.is_ready=True;self.engine.tick(self.now+2);self.assertEqual(self.engine.load()['survival']['phase'],'running');self.assertFalse((self.root/'inbox/survival.wake').exists())
 def test_manual_close_does_not_kick_player(self):self.heartbeat(1);self.engine.intent('close','survival',self.now);self.engine.tick(self.now);self.assertFalse(self.driver.calls);self.assertTrue(self.engine.load()['survival']['closed'])
 def test_closed_idle_mode_never_wakes(self):self.sleeping();self.engine.intent('close','survival',self.now);self.wake();self.engine.tick(self.now);self.assertFalse(self.driver.calls);self.assertEqual(self.engine.load()['survival']['phase'],'closed')
 def test_closed_running_mode_stops_only_when_empty(self):self.engine.intent('close','survival',self.now);self.engine.tick(self.now);self.assertEqual(self.driver.calls,[('stop','survival')]);self.assertEqual(self.engine.load()['survival']['phase'],'closed')
 def test_open_explicitly_allows_wake_again(self):self.sleeping();self.engine.intent('close','survival',self.now);self.engine.tick(self.now);self.engine.intent('open','survival',self.now);self.wake();self.engine.tick(self.now);self.assertEqual(self.driver.calls,[('start','survival')])
 def test_unmarked_inactive_service_cannot_be_woken(self):self.driver.states['survival']='inactive';self.wake();self.engine.tick(self.now);self.assertFalse(self.driver.calls);self.assertEqual(self.engine.load()['survival']['phase'],'unavailable')
 def test_expired_request_does_not_start(self):self.sleeping();self.wake();self.engine.tick(self.now+301);self.assertFalse(self.driver.calls)
 def test_start_failure_remains_unavailable(self):self.sleeping();self.wake();self.engine.tick(self.now);self.driver.states['survival']='failed';self.engine.tick(self.now+1);self.assertEqual(self.engine.load()['survival']['phase'],'unavailable')
 def test_start_timeout_cannot_claim_ready(self):self.sleeping();self.wake();self.engine.tick(self.now);self.engine.tick(self.now+181);self.assertEqual(self.engine.load()['survival']['phase'],'unavailable')
 def test_restart_keeps_sleep_state(self):self.sleeping();other=m.Engine(self.config,self.driver);self.wake();other.tick(self.now);self.assertEqual(self.driver.calls,[('start','survival')])
 def test_interrupted_stop_is_reconciled_without_repeat(self):
  rows=self.engine.load();rows['survival']['phase']='stopping';m.atomic(self.engine.ledger,rows);self.driver.states['survival']='inactive';self.engine.tick(self.now);self.assertEqual(self.engine.load()['survival']['phase'],'sleeping');self.assertFalse(self.driver.calls)
 def test_clock_rollback_cannot_trigger_stop(self):self.now-=100;self.heartbeat();self.engine.tick(self.now);self.assertFalse(self.driver.calls)
 def test_force_sleep_is_pending_while_busy(self):self.engine.intent('sleep','survival',self.now);self.heartbeat(1);self.engine.tick(self.now);self.assertFalse(self.driver.calls);self.heartbeat(0);self.engine.tick(self.now+1);self.assertEqual(self.driver.calls,[('stop','survival')])
 def test_invalid_mode_intent_refused(self):self.assertRaises(ValueError,self.engine.intent,'open','lobby',self.now)
 def test_no_gate_leak_after_stop_error(self):
  self.due()
  with patch.object(self.driver,'stop',side_effect=RuntimeError('fixture')):self.assertRaises(RuntimeError,self.engine.tick,self.now)
  self.assertFalse(self.driver.gated)

class ValidationTests(unittest.TestCase):
 def setUp(self): self.config={'enabled':False,'ipcRoot':str(Path(tempfile.gettempdir())/'modesleep-fixture'/'ipc'),'modes':[{'id':'arena','unit':'minecraft-arena.service','port':25602}]}
 def test_example_valid(self):self.assertEqual(m.validate(self.config),self.config)
 def test_shell_unit_refused(self):self.config['modes'][0]['unit']='x;shutdown.service';self.assertRaises(ValueError,m.validate,self.config)
 def test_lobby_id_refused(self):self.config['modes'][0]['id']='lobby';self.assertRaises(ValueError,m.validate,self.config)
 def test_proxy_id_refused(self):self.config['modes'][0]['id']='proxy';self.assertRaises(ValueError,m.validate,self.config)
 def test_protected_port_refused(self):self.config['modes'][0]['port']=25565;self.assertRaises(ValueError,m.validate,self.config)
 def test_duplicate_service_refused(self):self.config['modes'].append({'id':'other','unit':'minecraft-arena.service','port':25603});self.assertRaises(ValueError,m.validate,self.config)
 def test_duplicate_port_refused(self):self.config['modes'].append({'id':'other','unit':'minecraft-other.service','port':25602});self.assertRaises(ValueError,m.validate,self.config)
 def test_relative_ipc_refused(self):self.config['ipcRoot']='runtime';self.assertRaises(ValueError,m.validate,self.config)
 def test_protected_unit_refused(self):self.config['modes'][0]['unit']='velocity.service';self.assertRaises(ValueError,m.validate,self.config)
 def test_custom_protected_unit_refused(self):self.config['protectedUnits']=['custom-lobby.service'];self.config['modes'][0]['unit']='custom-lobby.service';self.assertRaises(ValueError,m.validate,self.config)
 def test_nonobject_config_refused(self):self.assertRaises(ValueError,m.validate,[])
 def test_gate_tokens_cannot_inject_args(self):self.assertRaises(ValueError,m.Gate.spec,25601,'bad;token')
 def test_varint_roundtrip(self):
  import io
  for n in [0,1,127,128,65536,2147483647]:self.assertEqual(m.read_varint(io.BytesIO(m.varint(n))),n)

if __name__=='__main__':unittest.main()
