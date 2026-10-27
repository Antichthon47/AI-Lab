"""Bubblewrap policy. Reject unknown helper bytes, permissions, or broad mounts."""
import hashlib
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path("/usr/local/libexec/ai-lab-expense-bwrap")
HASH = "e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71"


def check_helper():
    if hashlib.sha256(Path("/usr/bin/bwrap").read_bytes()).hexdigest() != HASH:
        raise RuntimeError("system Bubblewrap changed; review and refresh the dedicated helper")
    for path in (HELPER.parent, *HELPER.parent.parents):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("unsafe helper parent: " + str(path))
    info = HELPER.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 1000
            or stat.S_IMODE(info.st_mode) != 0o750 or hashlib.sha256(HELPER.read_bytes()).hexdigest() != HASH):
        raise RuntimeError("dedicated helper ownership/mode/hash verification failed")
    policy = Path("/etc/apparmor.d/ai-lab-expense-bwrap")
    info = policy.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o644
            or policy.read_bytes() != (ROOT/"security/ai-lab-expense-bwrap.apparmor").read_bytes()):
        raise RuntimeError("dedicated profile ownership/mode/content verification failed")
    if Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns").read_text().strip() != "1":
        raise RuntimeError("global namespace restriction must remain enabled")


def sandbox(work, *, tests=False, runtime=(), host_network=False, state=None, broker=None, probe_files=()):
    if host_network:
        raise ValueError("host networking is forbidden; use the restricted Ollama bridge")
    if tests and (state or broker or runtime):
        raise ValueError("evaluator cannot mount agent state, runtimes, or broker")
    check_helper()
    work = Path(work).resolve(strict=True)
    if not work.is_dir() or work == ROOT or (ROOT/"trusted").is_relative_to(work) or work.is_relative_to(ROOT/"trusted"):
        raise ValueError("unsafe project mount")
    command = [str(HELPER), "--die-with-parent", "--new-session", "--unshare-all", "--unshare-user",
               "--disable-userns", "--assert-userns-disabled", "--cap-drop", "ALL",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--dir", "/home", "--tmpfs", "/home/agent", "--dir", "/etc",
               "--bind", str(work), "/work", "--chdir", "/work", "--clearenv",
               "--setenv", "HOME", "/home/agent", "--setenv", "PATH", "/usr/bin:/bin",
               "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--ro-bind", "/dev/null", str(HELPER)]
    if Path("/etc/ld.so.cache").exists():
        command += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    if state:
        state = Path(state).resolve(strict=True)
        if not state.is_dir() or state == work or (ROOT/"trusted").is_relative_to(state):
            raise ValueError("unsafe state mount")
        command += ["--bind", str(state), "/agent-state", "--setenv", "PI_CODING_AGENT_DIR", "/agent-state/pi",
                    "--setenv", "CODEX_HOME", "/agent-state/codex"]
    for name in runtime:
        path = Path(name).resolve(strict=True)
        allowed = (Path.home()/".nvm/versions/node", Path.home()/".pi/agent/install/releases",
                   Path.home()/".codex/packages/standalone")
        if not path.is_dir() or not any(path != parent and path.is_relative_to(parent) for parent in allowed):
            raise ValueError("runtime must be a version-specific approved installation")
        command += ["--ro-bind", str(path), str(path)]
    if tests:
        command += ["--ro-bind", str(ROOT/"trusted/regression"), "/tests",
                    "--ro-bind", str(ROOT/"trusted/evaluate.py"), "/evaluate.py"]
    if broker:
        broker = Path(broker).resolve(strict=True)
        if {p.name for p in broker.iterdir()} != {"ollama.sock"} or not stat.S_ISSOCK((broker/"ollama.sock").stat().st_mode):
            raise ValueError("broker mount must contain only its Unix socket")
        command += ["--ro-bind", str(broker), "/broker", "--ro-bind", str(ROOT/"security/bridge.py"), "/bridge.py",
                    "--setenv", "OLLAMA_HOST", "http://127.0.0.1:11435"]
    for source, target in probe_files:
        command += ["--ro-bind", str(source), target]
    command += ["--remount-ro", "/"]
    return command


def payload(command, broker=None):
    if broker:
        return ["/usr/bin/python3", "-I", "-B", "/bridge.py", "--socket", "/broker/ollama.sock", "--", *command]
    return command
