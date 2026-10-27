"""Trusted host-side isolation checks. Never make inference requests."""
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time

from .isolation import ROOT, payload, sandbox
from .bridge import Broker


def probe(work, output, runtime=(), host_network=False, state=None, *, tests=False,
          broker=None, capture_fn=None):
    if host_network:
        raise ValueError("host networking is forbidden")
    if capture_fn is None:
        raise ValueError("capture function required")
    work = Path(work).resolve()
    with tempfile.TemporaryDirectory(prefix="expense-probe-") as temp, socket.socket() as listener:
        temp = Path(temp)
        sentinel = temp/"host-private-sentinel"
        sentinel.write_text("host-only-control")
        assert sentinel.read_text() == "host-only-control"
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        with socket.create_connection(listener.getsockname(), timeout=2):
            positive, _ = listener.accept()
            positive.close()
        link = work/".probe-host-link"
        link.symlink_to(sentinel)
        forbidden = [str(ROOT/"trusted/reference/expense_tracker/__init__.py"),
                     str(ROOT/"trusted/regression/test_acceptance.py"), str(sentinel),
                     "/work/.probe-host-link", "/work/../"+str(sentinel).lstrip("/"),
                     "/etc/shadow", str(Path.home()/".codex/config.toml"),
                     str(Path.home()/".codex/auth.json"), str(Path.home()/".pi/agent/auth.json"),
                     str(Path.home()/".aws/credentials"), str(Path.home()/".ssh/id_ed25519")]
        if not tests:
            forbidden += ["/tests/test_acceptance.py", "/evaluate.py"]
        spec = {"forbidden": forbidden, "sentinel": str(sentinel), "tests": tests,
                "bridge": bool(broker), "host_port": listener.getsockname()[1],
                "namespaces": {n:os.readlink("/proc/self/ns/"+n) for n in ("pid","net","mnt","user")}}
        spec_file=temp/"spec.json"
        spec_file.write_text(json.dumps(spec))
        command=sandbox(work,tests=tests,runtime=runtime,state=state,broker=broker,
                        probe_files=[(ROOT/"security/probe_payload.py","/probe.py"),
                                     (spec_file,"/probe-spec.json")])
        command += payload(["/usr/bin/python3","-I","-B","/probe.py"],broker)
        try:
            result=capture_fn(command,Path(output),20,limits=True,memory_mb=512)
        finally:
            link.unlink(missing_ok=True)
        if sentinel.read_text() != "host-only-control":
            raise RuntimeError("host sentinel modified")
        if result["exit_status"] or result["timed_out"]:
            raise RuntimeError("isolation probe failed; no agent/candidate may execute")
        record=json.loads((Path(output)/"stdout.log").read_text())
        if record.get("passed") is not True:
            raise RuntimeError("invalid trusted isolation result")
        return result


def cleanup_probe(work, output, capture_fn):
    heartbeat=Path(work)/"heartbeat"
    code=("import os,time\nfrom pathlib import Path\n"
          "if os.fork()==0:\n os.setsid()\n while True:\n  Path('/work/heartbeat').write_text(str(time.monotonic()))\n  time.sleep(0.05)\n"
          "else:\n time.sleep(60)\n")
    result=capture_fn(sandbox(work)+["/usr/bin/python3","-I","-c",code],Path(output),2,limits=True,memory_mb=512)
    if not result["timed_out"] or not heartbeat.exists():
        raise RuntimeError("cleanup probe did not exercise a running detached descendant")
    before=heartbeat.read_text()
    time.sleep(0.5)
    if heartbeat.read_text() != before:
        raise RuntimeError("detached child survived namespace termination")
    return {"passed":True,"detached_child_heartbeat_stopped":True}


def validate(output, capture_fn, runtime=()):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    result={"passed":False,"agent_runs":0,"inference_requests":0}
    try:
        # Exercise the transport's allow/deny cases against fake upstreams before
        # permitting any real client. Isolated import mode avoids cwd imports.
        code=("import sys,unittest;sys.path.insert(0,"+repr(str(ROOT))+");"
              "suite=unittest.defaultTestLoader.discover("+repr(str(ROOT/"trusted"))+",pattern='test_bridge.py');"
              "result=unittest.TextTestRunner(verbosity=2).run(suite);"
              "sys.exit(0 if result.wasSuccessful() and result.testsRun>=20 else 1)")
        transport=capture_fn([sys.executable,"-I","-B","-c",code],output/"transport",30,limits=True,memory_mb=512)
        if transport["exit_status"] or transport["timed_out"]:
            raise RuntimeError("offline broker conformance gate failed")
        result["transport_gate"]=transport
        with tempfile.TemporaryDirectory(prefix="expense-offline-validation-") as temp:
            temp=Path(temp)
            work=temp/"work"; work.mkdir()
            state=temp/"state"
            (state/"pi").mkdir(parents=True)
            (state/"codex").mkdir()
            shutil.copyfile(ROOT/"configs/pi-models.json",state/"pi/models.json")
            shutil.copyfile(ROOT/"configs/codex-config.toml",state/"codex/config.toml")
            result["agent_layout"]=probe(work,output/"agent-layout",runtime=runtime,state=state,capture_fn=capture_fn)
            result["evaluator_layout"]=probe(work,output/"evaluator-layout",tests=True,capture_fn=capture_fn)
            broker_dir=temp/"broker"; broker_dir.mkdir(mode=0o700)
            # A guard also prevents any accidental upstream contact in this
            # validation. /healthz and denied routes are handled locally.
            def forbidden_upstream():
                raise RuntimeError("offline test attempted upstream connection")
            with Broker(broker_dir,upstream=forbidden_upstream):
                result["bridge_layout"]=probe(work,output/"bridge-layout",runtime=runtime,state=state,broker=broker_dir,capture_fn=capture_fn)
            result["process_cleanup"]=cleanup_probe(work,output/"cleanup",capture_fn)
        result["passed"]=True
    except Exception as exc:
        result["error"]=str(exc)
    (output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    if not result["passed"]:
        raise RuntimeError("offline isolation validation failed: "+result.get("error","unknown"))
    return result
