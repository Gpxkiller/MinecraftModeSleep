"""Real netfilter proof, ONLY in a disposable network namespace in CI.

Never modifies the host namespace firewall, never starts a real game service.
"""
import os, socket, socketserver, subprocess, tempfile, threading, unittest
from pathlib import Path
from test_engine import m

ALLOWED=(os.name=='posix' and os.environ.get('MODESLEEP_NETNS_TEST')=='1'
         and hasattr(os,'geteuid') and os.geteuid()==0
         and os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net'))

class Echo(socketserver.BaseRequestHandler):
 def handle(self):
  while data:=self.request.recv(128):self.request.sendall(data)
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True

@unittest.skipUnless(ALLOWED,'Explicit root test in a separate network namespace required')
class KernelTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
  self.a=Server(('127.0.0.1',0),Echo);self.b=Server(('127.0.0.1',0),Echo)
  for s in(self.a,self.b):threading.Thread(target=s.serve_forever,daemon=True).start()
  self.port=self.a.server_address[1];self.other=self.b.server_address[1]
  self.before=m.Gate.command(['-S','INPUT']).stdout
 def tearDown(self):
  m.Gate.recover(self.directory)
  self.assertEqual(m.Gate.command(['-S','INPUT']).stdout,self.before)
  for s in(self.a,self.b):s.shutdown();s.server_close()
  self.tmp.cleanup()
 def test_blocks_only_new_target_connections_keeps_existing_and_other_mode(self):
  with socket.create_connection(('127.0.0.1',self.port),timeout=1) as existing:
   with m.Gate(self.directory,self.port):
    existing.sendall(b'preserved');self.assertEqual(existing.recv(32),b'preserved')
    self.assertGreater(m.tcp_inventory(self.port)[0],0)
    with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',self.port),timeout=.5)
    with socket.create_connection(('127.0.0.1',self.other),timeout=1) as other:other.sendall(b'ok');self.assertEqual(other.recv(2),b'ok')
  with socket.create_connection(('127.0.0.1',self.port),timeout=1):pass
 def test_crash_lease_recovery_removes_only_owned_rule(self):
  gate=m.Gate(self.directory,self.port);gate.__enter__();self.assertTrue(gate.lease.exists());m.Gate.recover(self.directory);self.assertFalse(gate.lease.exists())
  with socket.create_connection(('127.0.0.1',self.port),timeout=1):pass
 def test_exception_removes_gate(self):
  with self.assertRaises(RuntimeError):
   with m.Gate(self.directory,self.port):raise RuntimeError('fixture')
  self.assertFalse(list(self.directory.glob('gate-*.json')))

if __name__=='__main__':unittest.main()
