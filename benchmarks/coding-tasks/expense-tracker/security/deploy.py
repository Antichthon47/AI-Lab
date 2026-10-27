"""Administrator-only installer for the exact reviewed helper and profile."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

DIRECTORY = Path(__file__).resolve().parent
DEST = Path("/usr/local/libexec/ai-lab-expense-bwrap")
POLICY = Path("/etc/apparmor.d/ai-lab-expense-bwrap")
SOURCE = Path("/usr/bin/bwrap")
EXPECTED = "e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71"
PROFILE = b"abi <abi/4.0>,\ninclude <tunables/global>\n\nprofile ai-lab-expense-bwrap /usr/local/libexec/ai-lab-expense-bwrap flags=(unconfined) {\n  userns,\n}\n"


def safe_parent(path):
    for parent in [path, *path.parents]:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("unsafe system directory: " + str(parent))


def install():
    if DEST.exists() or DEST.is_symlink() or POLICY.exists() or POLICY.is_symlink():
        raise RuntimeError("destination already exists; refusing to overwrite")
    safe_parent(Path("/usr/local"))
    safe_parent(Path("/etc/apparmor.d"))
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED:
        raise RuntimeError("system bwrap changed; review a fresh source hash")
    if (DIRECTORY/"ai-lab-expense-bwrap.apparmor").read_bytes() != PROFILE:
        raise RuntimeError("profile differs from exact reviewed contents")
    subprocess.run(["/usr/sbin/apparmor_parser", "-Q", "-K", str(DIRECTORY/"ai-lab-expense-bwrap.apparmor")], check=True)
    if not DEST.parent.exists():
        DEST.parent.mkdir(mode=0o755)
    safe_parent(DEST.parent)
    with DEST.open("xb") as f:
        f.write(source)
    os.chown(DEST, 0, 1000)
    DEST.chmod(0o750)
    with POLICY.open("xb") as f:
        f.write(PROFILE)
    os.chown(POLICY, 0, 0)
    POLICY.chmod(0o644)
    subprocess.run(["/usr/sbin/apparmor_parser", "-a", "-K", str(POLICY)], check=True)
    if Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns").read_text().strip() != "1":
        raise RuntimeError("global namespace restriction is not enabled")
    print("Installed approved helper/profile; global restriction remains 1.")


def rollback():
    if POLICY.is_symlink() or DEST.is_symlink():
        raise RuntimeError("refusing rollback of symlink")
    if POLICY.read_bytes() != PROFILE or hashlib.sha256(DEST.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError("installed contents differ; manual review required")
    if POLICY.stat().st_uid != 0 or DEST.stat().st_uid != 0:
        raise RuntimeError("unexpected owner")
    subprocess.run(["/usr/sbin/apparmor_parser", "-R", "-K", str(POLICY)], check=True)
    POLICY.unlink()
    DEST.unlink()
    print("Removed only benchmark profile/helper; retained parent directory and system bwrap.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Administrator authentication required; do not run agents as root.")
    if sys.argv[1:] == ["install"]:
        install()
    elif sys.argv[1:] == ["rollback"]:
        rollback()
    else:
        raise SystemExit("usage: deploy.py install|rollback")
