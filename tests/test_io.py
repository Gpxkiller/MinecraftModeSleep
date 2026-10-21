import contextlib, io, json, os, socket, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from test_engine import m

class InventoryTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.proc=Path(self.tmp.name);self.header='  sl  local_address rem_address st\n';self.write('','')
 def tearDown(self):self.tmp.cleanup()
 def write(self,v4,v6):(self.proc/'tcp').write_text(self.header+v4);(self.proc/'tcp6').write_text(self.header+v6)
 def row(self,addr='0100007F',state='0A',port=25601):return f'  0: {addr}:{port:04X} 00000000:0000 {state}\n'
 def test_empty_loopback_listener(self):self.write(self.row(),'');self.assertEqual(m.tcp_inventory(25601,self.proc),(0,1))
 def test_established_and_connecting_count(self):self.write(self.row()+self.row(state='01')+self.row(state='03'),'');self.assertEqual(m.tcp_inventory(25601,self.proc),(2,1))
 def test_other_port_does_not_count(self):self.write(self.row()+self.row(state='01',port=25602),'');self.assertEqual(m.tcp_inventory(25601,self.proc),(0,1))
 def test_time_wait_does_not_count(self):self.write(self.row()+self.row(state='06'),'');self.assertEqual(m.tcp_inventory(25601,self.proc),(0,1))
 def test_public_listener_refused(self):self.write(self.row(addr='00000000'),'');self.assertRaises(ValueError,m.tcp_inventory,25601,self.proc)
 def test_ipv6_listener_refused(self):self.write('',self.row(addr='00000000000000000000000001000000'));self.assertRaises(ValueError,m.tcp_inventory,25601,self.proc)
 def test_unknown_state_refused(self):self.write(self.row(state='FF'),'');self.assertRaises(ValueError,m.tcp_inventory,25601,self.proc)
 def test_malformed_inventory_refused(self):(self.proc/'tcp').write_text('not a tcp inventory');self.assertRaises(ValueError,m.tcp_inventory,25601,self.proc)

class StorageTests(unittest.TestCase):
 def test_atomic_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.json';m.atomic(p,{'a':1});self.assertEqual(m.read_json(p),{'a':1});self.assertEqual(len(list(Path(d).iterdir())),1)
 def test_bounded_read(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x';p.write_text('x'*1025);self.assertRaises(ValueError,m.read_json,p,1024)
 @unittest.skipIf(os.name=='nt','Windows symlink privilege not required for portable tests')
 def test_symlink_refused(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'actual';p.write_text('{}');link=Path(d)/'link';link.symlink_to(p);self.assertRaises(ValueError,m.read_json,link)

class ProtocolTests(unittest.TestCase):
 def serve(self,payload):
  listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
  def send():
   try:
    conn,_=listener.accept()
    with conn:
     conn.recv(1024)
     body=b'\0'+m.varint(len(payload))+payload
     conn.sendall(m.varint(len(body))+body)
   finally:listener.close()
  thread=threading.Thread(target=send,daemon=True);thread.start()
  with patch.object(m,'tcp_inventory',return_value=(0,1)):
   result=m.LinuxDriver(Path('.')).ready({'port':port})
  thread.join(3);return result
 def test_real_loopback_status_response(self):self.assertTrue(self.serve(json.dumps({'version':{'name':'Fixture'},'players':{'online':0}}).encode()))
 def test_invalid_json_cannot_claim_ready(self):self.assertFalse(self.serve(b'not-json'))
 def test_list_response_cannot_claim_ready(self):self.assertFalse(self.serve(b'[]'))
 def test_negative_player_count_cannot_claim_ready(self):self.assertFalse(self.serve(b'{"version":{},"players":{"online":-1}}'))
 def test_varint_too_long_refused(self):self.assertRaises(ValueError,m.read_varint,io.BytesIO(b'\xff'*6))
 def test_truncated_varint_refused(self):self.assertRaises(EOFError,m.read_varint,io.BytesIO(b'\x80'))

if __name__=='__main__':unittest.main()
