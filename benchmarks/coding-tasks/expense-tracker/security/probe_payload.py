"""Trusted sandbox probe; never loaded into an actual agent process."""
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

spec = json.loads(Path("/probe-spec.json").read_text())
for name in spec["forbidden"]:
    try:
        with open(name, "rb") as f:
            f.read(1)
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        pass
    else:
        raise RuntimeError("forbidden read succeeded: " + name)
for name in (spec["sentinel"], "/home/unrelated-write", "/etc/outside-write"):
    try:
        with open(name, "w") as f:
            f.write("BAD")
    except OSError:
        pass
    else:
        raise RuntimeError("outside write succeeded: " + name)
Path("/work/.probe-write").write_text("inside write succeeds")
assert Path("/work/.probe-write").read_text() == "inside write succeeds"
Path("/work/.probe-write").unlink()
try:
    Path("/usr/.expense-isolation-write").write_text("BAD")
except OSError as e:
    assert e.errno == errno.EROFS, str(e)
else:
    raise RuntimeError("runtime mount is writable")
assert Path("/usr/bin/python3").is_file()
try:
    assert Path("/usr/local/libexec/ai-lab-expense-bwrap").read_bytes() == b""
except PermissionError:
    pass  # A nodev/mode restriction on the /dev/null mask is also a denial.
if spec["tests"]:
    assert not Path("/agent-state").exists()
    assert Path("/tests/test_acceptance.py").is_file()
    try:
        Path("/tests/test_acceptance.py").open("a")
    except OSError as e:
        assert e.errno == errno.EROFS
    else:
        raise RuntimeError("hidden tests are writable")
else:
    assert not Path("/tests").exists() and not Path("/evaluate.py").exists()
    if Path("/agent-state").exists():
        Path("/agent-state/.probe-state").write_text("disposable-state")
        Path("/agent-state/.probe-state").unlink()
if not spec["bridge"]:
    assert not Path("/broker").exists() and not Path("/bridge.py").exists()
profile = Path("/proc/self/attr/current").read_text().strip()
assert profile == "ai-lab-expense-bwrap (unconfined)", profile
status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
assert status["NoNewPrivs"].strip() == "1"
assert int(status["CapEff"].strip(), 16) == 0
assert int(status["CapPrm"].strip(), 16) == 0
assert os.getuid() != 0, "payload must not run as root"
for namespace in ("net", "pid", "mnt", "user"):
    assert os.readlink("/proc/self/ns/" + namespace) != spec["namespaces"][namespace]
with socket.socket() as s:
    s.settimeout(1)
    assert s.connect_ex(("127.0.0.1", spec["host_port"])) != 0, "host listener reachable"
# UDP connect resolves routing without sending a packet or contacting a service.
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    try:
        s.connect(("192.0.2.1", 9))
    except OSError:
        pass
    else:
        raise RuntimeError("external route exists")
interfaces = {line.split(":", 1)[0].strip() for line in Path("/proc/net/dev").read_text().splitlines() if ":" in line}
assert interfaces <= {"lo"}, interfaces
try:
    s6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
except OSError as e:
    assert e.errno == errno.EAFNOSUPPORT
else:
    with s6:
        try:
            s6.connect(("2001:db8::1", 9))
        except OSError:
            pass
        else:
            raise RuntimeError("external IPv6 route exists")
nested = subprocess.run(["/usr/bin/unshare", "--user", "--map-root-user", "/usr/bin/true"], capture_output=True)
assert nested.returncode != 0, "nested namespaces unexpectedly allowed"
if spec["bridge"]:
    with urllib.request.urlopen("http://127.0.0.1:11435/healthz", timeout=5) as response:
        assert json.load(response) == {"ok": True}
    for path in ("/api/delete", "/api/pull", "/api/create", "/api/show"):
        try:
            urllib.request.urlopen("http://127.0.0.1:11435" + path, timeout=5)
        except urllib.error.HTTPError as e:
            assert e.code == 403
        else:
            raise RuntimeError("forbidden broker route accepted")
print(json.dumps({"passed": True, "profile": profile, "uid": os.getuid(), "network": "private",
                  "no_new_privileges": True, "capabilities": 0, "nested_userns": "denied",
                  "tests_layout": spec["tests"], "bridge": spec["bridge"]}))
