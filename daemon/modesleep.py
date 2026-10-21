"""Single-host, fail-closed Minecraft backend suspension. Standard library only.

No remote shell, no network control API, no Minecraft world access.
The engine accepts only locally configured systemd units and loopback ports.
"""
from __future__ import annotations
import argparse, contextlib, json, math, os, re, socket, stat, struct, subprocess, sys, time, uuid
from pathlib import Path

VERSION = '0.1.1'
ID = re.compile(r'[a-z][a-z0-9-]{0,39}\Z')
UNIT = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,100}\.service\Z')
BUSY = {'01', '02', '03', '04', '05', '08', '09', '0B', '0C'}

def safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symbolic links are refused')
    return path

def read_json(path, limit=1048576):
    path = safe(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('Regular IPC file required')
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('File too large')
    return json.loads(raw)

def atomic(path, value, mode=0o600):
    path = safe(path)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'w', encoding='utf8') as handle:
            if hasattr(os, 'fchmod'): os.fchmod(handle.fileno(), mode)
            json.dump(value, handle, allow_nan=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

def validate(config):
    if not isinstance(config, dict): raise ValueError('Object configuration required')
    if type(config.get('enabled')) is not bool:
        raise ValueError('enabled must be a boolean')
    root = Path(config.get('ipcRoot', ''))
    if not root.is_absolute() or len(root.parts) < 4:
        raise ValueError('An explicit dedicated absolute ipcRoot is required')
    safe(root)
    protected = config.get('protectedPorts', [25565, 25566])
    if not isinstance(protected, list) or any(type(p) is not int or not 1 <= p <= 65535 for p in protected):
        raise ValueError('Invalid protected ports')
    if not number(config.get('idleSeconds', 86400), 60, 31536000):
        raise ValueError('Invalid idle delay')
    modes = config.get('modes')
    if not isinstance(modes, list) or not 1 <= len(modes) <= 64:
        raise ValueError('Configure between one and 64 modes')
    protected_units = config.get('protectedUnits', [])
    if not isinstance(protected_units, list) or any(not isinstance(u, str) or not UNIT.fullmatch(u) for u in protected_units):
        raise ValueError('Invalid protected units')
    ids, units, ports = set(), set(protected_units) | {'minecraft-lobby.service', 'velocity.service'}, set(protected) | {25565, 25566}
    for m in modes:
        if not isinstance(m, dict) or not ID.fullmatch(m.get('id', '')) or m['id'] in {'lobby', 'proxy'} or m['id'] in ids:
            raise ValueError('Invalid or protected mode')
        if not UNIT.fullmatch(m.get('unit', '')) or m['unit'] in units:
            raise ValueError('Invalid or duplicate service')
        p = m.get('port')
        if type(p) is not int or not 1024 <= p <= 65535 or p in ports:
            raise ValueError('Invalid, duplicate or protected backend port')
        if not number(m.get('idleSeconds', config.get('idleSeconds', 86400)), 60, 31536000):
            raise ValueError('Invalid per-mode delay')
        ids.add(m['id']); units.add(m['unit']); ports.add(p)
    return config

def tcp_inventory(port, proc=Path('/proc/net')):
    """Count all physical sessions, including invisible/connecting players.

    Only an IPv4 127.0.0.1 listener is supported by the matching SYN gate.
    Any IPv6 or public listener on this port makes suspension unsafe.
    """
    busy, listeners = 0, 0
    for name in ('tcp', 'tcp6'):
        lines = (proc / name).read_text().splitlines()
        if not lines or 'local_address' not in lines[0]:
            raise ValueError('Unknown TCP inventory')
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] not in BUSY | {'06', '07', '0A'}:
                raise ValueError('Unknown TCP state')
            addr, raw_port = fields[1].split(':')
            if int(raw_port, 16) != port:
                continue
            if fields[3] == '0A':
                if name != 'tcp' or addr.upper() != '0100007F':
                    raise ValueError('Backend must listen exclusively on 127.0.0.1')
                listeners += 1
            elif fields[3] in BUSY:
                busy += 1
    return busy, listeners

class Engine:
    """Deterministic policy; all privileged operations are in the driver."""
    def __init__(self, config, driver):
        self.config = validate(config); self.driver = driver
        self.root = safe(config['ipcRoot'])
        self.ledger = self.root / 'private' / 'ledger.json'
        self.public = self.root / 'public' / 'status.json'

    def load(self):
        data = read_json(self.ledger) if self.ledger.exists() else {}
        if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
            raise ValueError('Invalid persistent state')
        return data

    def publish(self, data, now):
        atomic(self.ledger, data)
        rows = {m['id']: {'phase': data.get(m['id'], {}).get('phase', 'unavailable'),
                          'closed': data.get(m['id'], {}).get('closed', False), 'port': m['port']}
                for m in self.config['modes']}
        atomic(self.public, {'version': 1, 'enabled': self.config['enabled'], 'generatedAt': now, 'modes': rows}, 0o644)

    def intent(self, action, mode, now):
        if mode not in {m['id'] for m in self.config['modes']}:
            raise ValueError('Mode not configured')
        data = self.load(); row = data.setdefault(mode, {'phase': 'unavailable', 'lastBusy': now})
        if action == 'close':
            row['closed'] = True
            safe(self.root / 'inbox' / (mode + '.wake')).unlink(missing_ok=True)
        elif action == 'open':
            row['closed'] = False
            row.pop('sleepRequested', None)
            row['lastBusy'] = now
            if row['phase'] in ('closed', 'unavailable'):
                row['phase'] = 'sleeping'
        elif action == 'sleep':
            row['sleepRequested'] = True
        else:
            raise ValueError('Unknown action')
        self.publish(data, now)

    def tick(self, now):
        if not number(now, 0, 1e12):
            raise ValueError('Invalid clock')
        data = self.load()
        if not self.config['enabled']:
            self.publish(data, now); return
        try:
            heartbeat = read_json(self.root / 'inbox' / 'heartbeat.json')
        except (OSError, ValueError, TypeError):
            heartbeat = {}
        if not isinstance(heartbeat, dict): heartbeat = {}
        stamp = heartbeat.get('generatedAt')
        fresh = number(stamp, now - 30, now + 5)
        counts = heartbeat.get('counts', {})
        if not isinstance(counts, dict): counts = {}
        for mode in self.config['modes']:
            name, port = mode['id'], mode['port']
            row = data.setdefault(name, {'phase': 'unavailable', 'lastBusy': now})
            request = safe(self.root / 'inbox' / (name + '.wake'))
            if not number(row.get('lastBusy'), 0, now): row['lastBusy'] = now
            state = self.driver.active(mode)
            if row['phase'] == 'stopping':
                row['phase'] = ('closed' if row.get('closed') else 'sleeping') if state == 'inactive' else 'unavailable'
                row['lastBusy'] = now
            if row.get('closed'):
                request.unlink(missing_ok=True)
            if row['phase'] == 'starting':
                if row.get('closed'):
                    row['phase'] = 'running'; row['lastBusy'] = now
                elif state == 'active' and self.driver.ready(mode):
                    row['phase'] = 'running'; row['lastBusy'] = now
                    request.unlink(missing_ok=True)
                    self.driver.audit('wake-ready', name)
                elif not number(row.get('startAt'), now - 180, now + 5) or state == 'failed':
                    row['phase'] = 'unavailable'; self.driver.audit('wake-unconfirmed', name)
                continue
            if row.get('closed') and state == 'active':
                row['phase'] = 'running'
            if row['phase'] in ('sleeping', 'closed'):
                if row.get('closed'):
                    row['phase'] = 'closed'; continue
                if state == 'active':
                    # External starts are adopted only after readiness is proven.
                    if self.driver.ready(mode): row.update(phase='running', lastBusy=now)
                    continue
                if request.exists():
                    info = request.lstat()
                    valid = stat.S_ISREG(info.st_mode) and number(info.st_mtime, now - 300, now + 5) and info.st_size <= 64
                    if not valid:
                        request.unlink(missing_ok=True); continue
                    if state == 'inactive':
                        row.update(phase='starting', startAt=now)
                        self.publish(data, now)  # Persist authority before starting.
                        self.driver.start(mode); self.driver.audit('wake-start', name)
                continue
            request.unlink(missing_ok=True)  # An unmarked service cannot be woken by proxy data.
            if state != 'active':
                row['phase'] = 'unavailable'; row['lastBusy'] = now; continue
            row['phase'] = 'running'
            count = counts.get(name)
            if not fresh or type(count) is not int or count < 0 or count > 0:
                row['lastBusy'] = now; continue
            delay = mode.get('idleSeconds', self.config.get('idleSeconds', 86400))
            if not row.get('closed') and not row.get('sleepRequested') and now - row['lastBusy'] < delay:
                continue
            with self.driver.gate(port) as gate:
                busy, listeners = self.driver.inventory(port)
                if busy or listeners != 1:
                    row['lastBusy'] = now; continue
                gate.verify()
                row['phase'] = 'stopping'; self.publish(data, now)
                self.driver.stop(mode)
                if self.driver.active(mode) != 'inactive':
                    raise RuntimeError('Stop not confirmed; no automatic restart')
                row['phase'] = 'closed' if row.get('closed') else 'sleeping'
                row.pop('sleepRequested', None)
                self.driver.audit('closed' if row.get('closed') else 'sleep', name)
        self.publish(data, now)

def systemctl(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True, text=True, timeout=180)

class LinuxDriver:
    def __init__(self, root): self.root = root
    def active(self, m): return systemctl('show', m['unit'], '-p', 'ActiveState', '--value').stdout.strip()
    def start(self, m): systemctl('start', '--no-block', m['unit'])
    def stop(self, m): systemctl('stop', m['unit'])
    def inventory(self, port): return tcp_inventory(port)
    def gate(self, port): return Gate(self.root / 'private', port)
    def audit(self, action, mode):
        # Only configured mode identifiers, never player names or credentials.
        print(json.dumps({'at': time.time(), 'action': action, 'mode': mode}), flush=True)
    def ready(self, mode):
        try:
            if tcp_inventory(mode['port'])[1] != 1: return False
            with socket.create_connection(('127.0.0.1', mode['port']), timeout=2) as conn:
                conn.settimeout(2)
                host = b'localhost'
                handshake = b'\x00' + varint(0) + varint(len(host)) + host + struct.pack('>H', mode['port']) + b'\x01'
                conn.sendall(varint(len(handshake)) + handshake + b'\x01\x00')
                length = read_varint(conn)
                if not 2 <= length <= 65536: return False
                raw = receive(conn, length)
                if raw[0] != 0: return False
                import io
                buffer = io.BytesIO(raw[1:])
                size = read_varint(buffer)
                if not 1 <= size <= 65536: return False
                payload = buffer.read(size)
                if len(payload) != size or buffer.read(1): return False
                status = json.loads(payload)
                return isinstance(status, dict) and isinstance(status.get('version'), dict) and isinstance(status.get('players'), dict) and type(status['players'].get('online')) is int and status['players']['online'] >= 0
        except (OSError, ValueError, EOFError, TypeError): return False

def varint(n):
    out = bytearray()
    while True:
        value = n & 127; n >>= 7; out.append(value | (128 if n else 0))
        if not n: return bytes(out)

def receive(stream, n):
    result = b''
    while len(result) < n:
        chunk = stream.recv(n - len(result)) if hasattr(stream, 'recv') else stream.read(n - len(result))
        if not chunk: raise EOFError('Incomplete response')
        result += chunk
    return result

def read_varint(stream):
    result = 0
    for i in range(5):
        byte = receive(stream, 1)[0]; result |= (byte & 127) << (i * 7)
        if not byte & 128: return result
    raise ValueError('Oversized VarInt')

class Gate:
    """Exact-token, temporary loopback SYN gate. Never flushes a firewall."""
    def __init__(self, directory, port):
        self.directory = directory; self.port = port; self.token = uuid.uuid4().hex
        self.lease = directory / ('gate-' + self.token + '.json')
    @staticmethod
    def spec(port, token):
        if type(port) is not int or not 1024 <= port <= 65535 or not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('Invalid gate')
        return ['-i', 'lo', '-d', '127.0.0.1/32', '-p', 'tcp', '--dport', str(port), '--syn', '-m', 'comment', '--comment', 'modesleep-' + token, '-j', 'REJECT', '--reject-with', 'tcp-reset']
    @staticmethod
    def command(args):
        return subprocess.run(['/usr/sbin/iptables', '-w', '5', *args], capture_output=True, timeout=10)
    def verify(self):
        if self.command(['-C', 'INPUT', *self.spec(self.port, self.token)]).returncode:
            raise RuntimeError('Admission gate missing')
    def __enter__(self):
        atomic(self.lease, {'port': self.port, 'token': self.token})
        try:
            if self.command(['-I', 'INPUT', '1', *self.spec(self.port, self.token)]).returncode:
                raise RuntimeError('Cannot establish admission gate')
            self.verify(); return self
        except BaseException:
            self.__exit__(None, None, None); raise
    def __exit__(self, *args):
        code = self.command(['-C', 'INPUT', *self.spec(self.port, self.token)]).returncode
        if code == 0:
            if self.command(['-D', 'INPUT', *self.spec(self.port, self.token)]).returncode:
                raise RuntimeError('Cannot remove admission gate')
        elif code != 1: raise RuntimeError('Cannot verify admission release')
        if self.command(['-C', 'INPUT', *self.spec(self.port, self.token)]).returncode != 1:
            raise RuntimeError('Gate release not confirmed')
        self.lease.unlink(missing_ok=True)
    @classmethod
    def recover(cls, directory):
        # Caller holds the single worker lock, so previous owners are gone.
        for path in directory.glob('gate-*.json'):
            data = read_json(path, 1024)
            if path.name != 'gate-' + data['token'] + '.json': raise ValueError('Invalid lease')
            gate = cls(directory, data['port']); gate.token = data['token']; gate.lease = path
            gate.__exit__(None, None, None)

def secure_root(root):
    for parent in root.parents:
        st = safe(parent).stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError('IPC ancestors must be root-owned and not writable by others')
    for p in (root, root / 'private', root / 'public', root / 'inbox'):
        safe(p)
        st = p.stat()
        if not p.is_dir() or st.st_uid != 0 or st.st_mode & 0o002:
            raise ValueError('IPC directories must be root-owned, not world-writable')
        if p.name != 'inbox' and st.st_mode & 0o022:
            raise ValueError('Only the inbox may be group-writable')
    if (root / 'private').stat().st_mode & 0o077:
        raise ValueError('Private state must have mode 0700')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--apply', action='store_true', help='Explicitly permit systemd/firewall actions')
    parser.add_argument('action', choices=['check', 'tick', 'open', 'close', 'sleep'])
    parser.add_argument('mode', nargs='?'); args = parser.parse_args()
    config = validate(read_json(args.config, 65536))
    if args.action == 'check': print('Configuration valid; no service changed.'); return
    if not args.apply: raise ValueError('No action without --apply; use check for validation')
    if sys.platform != 'linux' or os.geteuid() != 0: raise ValueError('Linux root required')
    cfg = safe(args.config).stat()
    if cfg.st_uid != 0 or cfg.st_mode & 0o022: raise ValueError('Config must be root-owned and not writable by others')
    root = safe(config['ipcRoot']); secure_root(root)
    import fcntl
    with safe(root / 'private' / 'worker.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        Gate.recover(root / 'private')
        engine = Engine(config, LinuxDriver(root))
        if args.action == 'tick': engine.tick(time.time())
        else: engine.intent(args.action, args.mode, time.time())

if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError, TypeError) as error:
        print('ModeSleep refused operation: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
