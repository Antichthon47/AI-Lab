#!/usr/bin/env python3
"""Fail-closed benchmark orchestration. No agents are launched by validation."""
import argparse
from contextlib import nullcontext
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures/buggy"
TRUSTED = ROOT / "trusted"


def manifest(directory):
    result = {}
    for p in sorted(directory.rglob("*")):
        if p.is_symlink():
            raise ValueError("fixture must not contain symbolic links")
        if p.is_file() and "__pycache__" not in p.parts:
            result[str(p.relative_to(directory))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def clean_copy(destination):
    expected = json.loads((ROOT / "fixture-manifest.json").read_text())
    if manifest(FIXTURE) != expected:
        raise ValueError("buggy fixture differs from frozen manifest; refusing reset")
    shutil.copytree(FIXTURE, destination, ignore=shutil.ignore_patterns("__pycache__"))
    if manifest(destination) != expected:
        raise ValueError("reset did not reproduce fixture")
    return expected


def capture(command, directory, timeout, env=None, limits=False, memory_mb=None):
    directory.mkdir(parents=True, exist_ok=True)
    def set_limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout+1))
        if memory_mb:
            resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024*1024, memory_mb*1024*1024))
    start = time.monotonic()
    with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=env,
                                   start_new_session=True, preexec_fn=set_limits if limits else None)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
        finally:
            # Also terminate background descendants in the same process group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    record = {"command": command, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "elapsed_seconds": time.monotonic()-start, "exit_status": code, "timed_out": timed_out}
    (directory / "execution.json").write_text(json.dumps(record, indent=2)+"\n")
    return record


from security.isolation import sandbox, payload
from security.bridge import Broker
from security.probes import probe as trusted_probe, validate as validate_isolation


def probe(work, output, runtime=(), host_network=False, state=None, **kwargs):
    return trusted_probe(work, output, runtime, host_network, state, capture_fn=capture, **kwargs)


def validate():
    """Run only benchmark-author implementations, never an agent work directory."""
    report = ROOT/"validation"
    results = {}
    for label, project in [("reference", TRUSTED/"reference"), ("buggy", FIXTURE)]:
        run = capture([sys.executable, "-I", "-B", str(TRUSTED/"evaluate.py"),
                       "--project", str(project), "--tests", str(TRUSTED/"regression")], report/label, 30)
        results[label] = json.loads((report/label/"stdout.log").read_text())
        results[label]["exit_status"] = run["exit_status"]
    expected = json.loads((TRUSTED/"expected-failures.json").read_text())
    if not results["reference"]["successful"] or results["reference"]["tests_run"] < 20:
        raise RuntimeError("reference validation failed")
    if sorted(results["buggy"]["failures"]) != sorted(expected) or results["buggy"]["errors"]:
        raise RuntimeError("buggy failure set differs from intended failures")
    # Independently repair each mutated line, verifying the failed-test family
    # disappears while all other intentional failures remain.
    mutations=json.loads((TRUSTED/"mutations.json").read_text())
    with tempfile.TemporaryDirectory(prefix="expense-validation-") as temp:
        temp=Path(temp)
        for index, mutation in enumerate(mutations):
            project=temp/f"repair-{index}"
            clean_copy(project)
            source=project/"expense_tracker/__init__.py"
            source.write_text(source.read_text().replace(mutation["buggy"], mutation["correct"]))
            capture([sys.executable,"-I","-B",str(TRUSTED/"evaluate.py"),"--project",str(project),
                     "--tests",str(TRUSTED/"regression")], report/f"repair-{index}",30)
            repaired=json.loads((report/f"repair-{index}"/"stdout.log").read_text())
            remaining=[x for x in expected if mutation["test_class"] not in x]
            if sorted(repaired["failures"]) != sorted(remaining) or repaired["errors"]:
                raise RuntimeError("individual mutation validation failed")
        copies = [temp/"reset-a", temp/"reset-b"]
        a=clean_copy(copies[0]); b=clean_copy(copies[1])
        results["reset_identical"] = a == b
        try:
            probe(copies[0],report/"isolation")
            results["live_hidden_inaccessibility_verified"] = True
        except RuntimeError as exc:
            results["live_hidden_inaccessibility_verified"] = False
            results["isolation_limitation"] = str(exc)
    results["individual_mutations_verified"] = True
    results["agent_runs"] = 0
    (report/"summary.json").write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps(results,indent=2))
    if not results["live_hidden_inaccessibility_verified"]:
        raise RuntimeError("validation failed closed: hidden-read isolation not verified")


def prepare(name):
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
        raise ValueError("attempt name must use letters, digits, hyphens, underscores")
    attempt=ROOT/"attempts"/name
    attempt.mkdir(parents=True, exist_ok=False)
    original=clean_copy(attempt/"work")
    state=attempt/"agent-state"
    (state/"pi").mkdir(parents=True)
    (state/"codex").mkdir()
    shutil.copyfile(ROOT/"configs/pi-models.json",state/"pi/models.json")
    shutil.copyfile(ROOT/"configs/codex-config.toml",state/"codex/config.toml")
    (attempt/"initial-manifest.json").write_text(json.dumps(original,indent=2)+"\n")
    return attempt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="operation",required=True)
    sub.add_parser("validate")
    isolation_parser=sub.add_parser("validate-isolation")
    isolation_parser.add_argument("--runtime",action="append",default=[])
    p=sub.add_parser("prepare"); p.add_argument("name")
    p=sub.add_parser("run"); p.add_argument("name")
    p.add_argument("--approved",action="store_true",help="operator confirms explicit approval to launch agent and evaluate changes")
    p.add_argument("--runtime",action="append",default=[])
    p.add_argument("--ollama-bridge",action="store_true",help="private-namespace inference via restricted Unix broker; no host networking")
    p.add_argument("--timeout",type=int,default=600)
    argv=sys.argv[1:]
    command=[]
    if "--" in argv:
        split=argv.index("--")
        argv,command=argv[:split],argv[split+1:]
    args=parser.parse_args(argv)
    if args.operation=="validate": validate(); return
    if args.operation=="validate-isolation":
        print(json.dumps(validate_isolation(ROOT/"validation/security", capture,args.runtime),indent=2)); return
    if args.operation=="prepare": print(prepare(args.name)); return
    if not args.approved:
        parser.error("explicit approval is required; no agent or generated code was executed")
    if not command: parser.error("supply an agent command after --")
    if args.timeout < 1 or args.timeout > 3600: parser.error("timeout must be 1..3600")
    attempt=prepare(args.name); work=attempt/"work"
    # Full offline suite is a mandatory gate, not a stale cached approval.
    validate_isolation(attempt/"offline-gate", capture,args.runtime)
    state=attempt/"agent-state"
    with tempfile.TemporaryDirectory(prefix="expense-inference-broker-") as socket_dir:
        broker_dir=Path(socket_dir) if args.ollama_bridge else None
        if broker_dir:
            context=Broker(broker_dir)
        else:
            context=nullcontext()
        with context:
            probe(work,attempt/"agent-probe",runtime=args.runtime,state=state,broker=broker_dir)
            probe(work,attempt/"test-probe",tests=True)
            agent=capture(sandbox(work,runtime=args.runtime,state=state,broker=broker_dir)
                          +payload(command,broker_dir),attempt/"agent",args.timeout,limits=True)
    # Always evaluate after a nonzero exit/timeout; preserve the whole work tree.
    evaluation=capture(sandbox(work,tests=True)+["/usr/bin/python3","-I","-B","/evaluate.py",
                       "--project","/work","--tests","/tests"], attempt/"regression",30,limits=True,memory_mb=512)
    try:
        score=json.loads((attempt/"regression/stdout.log").read_text())
    except (ValueError,OSError):
        score={"passed":0,"scoring_error":"missing/invalid test report"}
    (attempt/"result.json").write_text(json.dumps({"agent":agent,"regression":evaluation,
                                                  "score":score},indent=2)+"\n")
    print(attempt/"result.json")


if __name__=="__main__":
    main()
