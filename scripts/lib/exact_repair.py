#!/usr/bin/env python3
"""Narrow exact single-source repair admission. Stdlib; never imports a provider.

Authority is a private host-issued, single-use PUBLIC FIXTURE TEST grant.
This is deliberately not a human approval or a general execution facility.
"""

import argparse
import hashlib
import json
import os
import re
import resource
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = (
    "scripts/mana-repair.sh",
    "scripts/mana-verify.sh",
    "scripts/lib/exact_repair.py",
    "scripts/lib/verification-exec.pl",
)
LIMIT = 262144


class Rejected(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Rejected(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return digest(encoded(value))


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def safe_absolute(raw):
    p = Path(raw)
    require(p.is_absolute() and str(p) == raw and ".." not in p.parts, "ABSOLUTE_PATH")
    for part in (p, *p.parents):
        require(not part.is_symlink(), "SYMLINK")
    require(p.resolve() == p, "NONCANONICAL_PATH")
    return p


def relative(raw):
    require(type(raw) is str and re.fullmatch(r"[A-Za-z0-9_./-]+", raw), "PATH")
    p = PurePosixPath(raw)
    require(
        not p.is_absolute() and str(p) == raw and all(x not in (".", "..") for x in p.parts), "PATH"
    )
    return raw


def read_file(path, limit=1048576, unique=True):
    p = safe_absolute(str(path))
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        require(
            stat.S_ISREG(s.st_mode) and (not unique or s.st_nlink == 1) and s.st_size <= limit,
            "FILE_LIMIT_OR_TYPE",
        )
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(limit + 1)
        require(len(data) <= limit, "FILE_LIMIT")
        return data
    finally:
        os.close(fd)


def load(path):
    return json.loads(
        read_file(path),
        object_pairs_hook=pairs,
        parse_constant=lambda _: require(False, "NONFINITE"),
    )


def private(path, directory=False):
    p = safe_absolute(str(path))
    s = p.stat()
    require(s.st_uid == os.getuid() and s.st_mode & 0o077 == 0, "PRIVATE_HOST_PATH_REQUIRED")
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode), "HOST_PATH_TYPE")
    if not directory:
        require(s.st_nlink == 1, "HOST_HARDLINK")
    return p


def runtime():
    base = subprocess.check_output(
        ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    files = {p: digest(read_file(ROOT / p)) for p in IMPLEMENTATION}
    jdk = safe_absolute(subprocess.check_output(["/usr/libexec/java_home"], text=True).strip())
    tools = {
        p: digest(read_file(Path(p).resolve(), 67108864, unique=False))
        for p in (
            sys.executable,
            str(Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"),
            "/usr/bin/perl",
            "/usr/bin/sandbox-exec",
            "/usr/bin/javac",
            "/usr/bin/java",
            str(jdk / "bin/java"),
            str(jdk / "bin/javac"),
        )
    }
    return {
        "base_revision": base,
        "files": files,
        "changes_identity": identity(files),
        "jdk_home": str(jdk),
        "tools": tools,
    }


def commands(request):
    """Fixed catalog: no executable, options or shell text from the proposal."""
    v = request["verification"]
    require(set(v) == {"catalog", "test_path", "main_class"}, "VERIFIER_FIELDS")
    require(v["catalog"] == "java-jdk-pair/v1", "CATALOG")
    test = relative(v["test_path"])
    require(test.startswith("src/test/java/") and test.endswith(".java"), "TEST_PATH")
    require(
        re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*", v["main_class"]),
        "MAIN_CLASS",
    )
    dest = Path(request["destination"])
    build = str(Path(request["outputs"]) / "classes")
    return [
        [
            "/usr/bin/javac",
            "-d",
            build,
            str(dest / request["proposal"]["edit"]["path"]),
            str(dest / test),
        ],
        ["/usr/bin/java", "-cp", build, v["main_class"]],
    ]


def validate(request, grant_path, actual_runtime):
    require(
        set(request)
        == {
            "schema",
            "id",
            "proposal",
            "destination",
            "destination_identity",
            "outputs",
            "result_sha256",
            "verification",
            "budget",
            "runtime",
            "authorization_reference",
            "protected_files",
            "provider",
            "operation",
            "baseline",
        },
        "REQUEST_FIELDS",
    )
    require(request["operation"] in ("repair-verify", "verify"), "OPERATION")
    require(
        request["schema"] == "mana.exact-request/v1" and request["provider"] == "none",
        "EXPLICIT_NO_PROVIDER",
    )
    require(
        type(request["id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request["id"]),
        "REQUEST_ID",
    )
    require(request["runtime"] == actual_runtime, "REVISION_NOT_ADMITTED")
    p = request["proposal"]
    require(
        p["schema"] == "mom.operator.offline-proposal/v1"
        and p["status"] == "HUMAN_REQUIRED"
        and p["executable"] is False,
        "HISTORICAL_PROPOSAL",
    )
    require(
        p["fingerprint"] == identity({k: v for k, v in p.items() if k != "fingerprint"}),
        "PROPOSAL_FINGERPRINT",
    )
    h = p["handoff"]
    require(
        h["schema"] == "mom.operator.offline-handoff/v1" and h["mission"] and h["request"], "ORIGIN"
    )
    snapshot = h["snapshot"]
    require(h["snapshot_sha256"] == identity(snapshot), "SNAPSHOT_HASH")
    require(set(p["edit"]) == {"path", "replacement"}, "EDIT_FIELDS")
    source = relative(p["edit"]["path"])
    require(
        source.startswith("src/main/java/")
        and source.endswith(".java")
        and not any(
            x.lower() in ("test", "tests", "config", "configuration")
            for x in PurePosixPath(source).parts
        ),
        "SOURCE_SCOPE",
    )
    text = p["edit"]["replacement"]
    require(
        type(text) is str and 0 < len(text.encode()) <= LIMIT and "\0" not in text, "REPLACEMENT"
    )
    require(digest(text.encode()) == request["result_sha256"], "RESULT_HASH")
    require(source in snapshot and text != snapshot[source]["text"], "EMPTY_OR_UNBASED_EDIT")
    dest = private(request["destination"], True)
    out = private(request["outputs"], True)
    require(not list(out.iterdir()), "OUTPUT_NOT_EMPTY")
    # Deliberately restricted to private, disposable external test copies.
    require(
        dest.is_relative_to(Path("/private/tmp")) and out.is_relative_to(Path("/private/tmp")),
        "DISPOSABLE_DESTINATION_REQUIRED",
    )
    require(not dest.is_relative_to(out) and not out.is_relative_to(dest), "OUTPUT_OVERLAP")
    ds = dest.stat()
    require(
        request["destination_identity"] == {"device": ds.st_dev, "inode": ds.st_ino},
        "DESTINATION_IDENTITY",
    )
    files = {}
    for file in dest.rglob("*"):
        require(not file.is_symlink(), "SYMLINK")
        if not file.is_dir():
            files[str(file.relative_to(dest))] = digest(read_file(file, LIMIT))
    require(set(files) == set(snapshot), "DESTINATION_SCOPE")
    for name, record in snapshot.items():
        relative(name)
        require(digest(record["text"].encode()) == record["sha256"] == files[name], "BASE_MISMATCH")
    baseline = request["baseline"]
    require(
        set(baseline) == {"test_exit", "stdout_sha256"}
        and type(baseline["test_exit"]) is int
        and 0 <= baseline["test_exit"] <= 255
        and re.fullmatch(r"[0-9a-f]{64}", baseline["stdout_sha256"]),
        "BASELINE_CONTRACT",
    )
    argv = commands(request)
    require(
        request["verification"]["test_path"] == h["regression_test"]
        and request["verification"]["test_path"] in snapshot,
        "FROZEN_TEST",
    )
    b = request["budget"]
    require(
        set(b)
        == {
            "attempts",
            "verification_commands",
            "timeout_seconds",
            "total_seconds",
            "output_bytes",
            "file_bytes",
        },
        "BUDGET_FIELDS",
    )
    require(
        all(type(v) is int for v in b.values())
        and b["attempts"] == 1
        and b["verification_commands"] == (4 if request["operation"] == "repair-verify" else 2)
        and 1 <= b["timeout_seconds"] <= 30
        and 1 <= b["total_seconds"] <= 180
        and 1024 <= b["output_bytes"] <= 65536
        and 1024 <= b["file_bytes"] <= 1048576,
        "BUDGET_EXHAUSTED_OR_INVALID",
    )
    require(b["total_seconds"] >= b["timeout_seconds"] * 6, "TOTAL_BUDGET")
    protected = request["protected_files"]
    require(type(protected) is list and 1 <= len(protected) <= 32, "PROTECTED_FILES")
    for name in protected:
        file = safe_absolute(name)
        require(not file.is_relative_to(dest) and not file.is_relative_to(out), "PROTECTED_OVERLAP")
        read_file(file)
    gp = private(grant_path)
    private(gp.parent, True)
    require(not gp.is_relative_to(dest) and not gp.is_relative_to(out), "AUTHORITY_OVERLAP")
    g = load(gp)
    require(
        set(g) == {"schema", "id", "authority", "approved", "request_sha256", "expires_at", "uses"},
        "GRANT_FIELDS",
    )
    require(
        g["schema"] == "mana.exact-host-grant/v1"
        and g["authority"] == "explicit-public-fixture-test",
        "TEST_AUTHORITY_REQUIRED",
    )
    require(
        g["approved"] is True and g["id"] == request["authorization_reference"],
        "AUTHORIZATION_ABSENT_OR_DENIED",
    )
    require(g["request_sha256"] == identity(request), "AUTHORIZATION_EFFECTS_MISMATCH")
    require(
        g["uses"] == 1
        and type(g["expires_at"]) is int
        and time.time() < g["expires_at"] <= time.time() + 3600,
        "AUTHORIZATION_EXPIRED_OR_BUDGET",
    )
    require(not Path(str(gp) + ".used").exists(), "AUTHORIZATION_CONSUMED")
    require(
        sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file(), "SEATBELT_REQUIRED"
    )
    return {"request": request, "grant": g, "grant_path": gp, "files": files, "argv": argv}


def policy(request):
    """Specific Seatbelt policy; no child creation, network or general write grant."""
    q = json.dumps
    dest, out = Path(request["destination"]), Path(request["outputs"])
    source = dest / request["proposal"]["edit"]["path"]
    reads = [
        "/System",
        "/usr",
        "/Library/Java",
        str(Path(sys.base_prefix).resolve()),
        str(Path(sys.executable).resolve().parent.parent),
        request["runtime"]["jdk_home"],
        str(dest),
        str(out / "classes"),
    ]
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            "(deny network*)",
            "(deny process-fork)",
            "(allow process-exec "
            + " ".join(
                "(literal " + q(str(Path(p).resolve())) + ")"
                for p in (
                    sys.executable,
                    str(Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"),
                    "/usr/bin/java",
                    "/usr/bin/javac",
                    request["runtime"]["jdk_home"] + "/bin/java",
                    request["runtime"]["jdk_home"] + "/bin/javac",
                )
            )
            + ")",
            "(allow sysctl-read)",
            "(allow file-read-metadata)",
            "(allow file-read* " + " ".join("(subpath " + q(p) + ")" for p in reads) + ")",
            "(allow file-read* (literal " + q(str(Path(__file__).resolve())) + "))",
            '(allow file-read* (literal "/dev/urandom") (literal "/dev/random") (literal "/"))',
            '(allow file-read* file-write-data (literal "/dev/null"))',
            "(allow file-write-data (literal " + q(str(source)) + "))",
            "(allow file-write* (subpath " + q(str(out / "classes")) + "))",
        ]
    )


def environment(request):
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": request["outputs"] + "/classes",
        "TMPDIR": request["outputs"] + "/classes",
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "JAVA_HOME": request["runtime"]["jdk_home"],
    }


def supervise(request, argv, label, sandbox=True):
    out = Path(request["outputs"])
    b = request["budget"]
    cmd = [
        "/usr/bin/perl",
        str(ROOT / "scripts/lib/verification-exec.pl"),
        "--timeout",
        str(b["timeout_seconds"]),
        "--output-cap",
        str(b["output_bytes"]),
        "--stdout",
        str(out / (label + ".stdout")),
        "--stderr",
        str(out / (label + ".stderr")),
        "--status",
        str(out / (label + ".status")),
        "--",
    ]
    if sandbox:
        cmd += ["/usr/bin/sandbox-exec", "-p", policy(request)]
    cmd += argv

    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (b["file_bytes"], b["file_bytes"]))
        resource.setrlimit(resource.RLIMIT_CPU, (b["timeout_seconds"], b["timeout_seconds"] + 1))
        os.umask(0o077)

    completed = subprocess.run(
        cmd,
        cwd=request["destination"],
        env=environment(request),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        preexec_fn=limits,
        timeout=b["timeout_seconds"] + 5,
    )
    require(
        completed.returncode == 0,
        "SUPERVISOR_FAILED:" + completed.stderr.decode(errors="replace")[:500],
    )
    status = [int(x) for x in (out / (label + ".status")).read_text().split()]
    return {
        "argv": argv,
        "cwd": request["destination"],
        "exit": status[0],
        "signal": status[1],
        "timeout": bool(status[2]),
        "descendants_terminated": bool(status[3]),
        "stdout_bytes": status[4],
        "stderr_bytes": status[5],
        "duration_ms": status[6],
        "stdout": (out / (label + ".stdout")).read_text(errors="replace"),
        "stderr": (out / (label + ".stderr")).read_text(errors="replace"),
    }


def passed(result):
    return result["exit"] == 0 and not result["timeout"] and not result["descendants_terminated"]


def probe(request):
    protected = (
        request["protected_files"]
        + [str(ROOT / p) for p in IMPLEMENTATION]
        + [request["outputs"] + "/control.json"]
        + [
            str(Path(request["destination"]) / p)
            for p in request["proposal"]["handoff"]["snapshot"]
            if p != request["proposal"]["edit"]["path"]
        ]
    )
    code = """import os,socket,json,errno
r={}
for p in PROTECTED:
 try:
  fd=os.open(p,os.O_WRONLY);os.close(fd);r[p]=False
 except OSError as e:r[p]=e.errno in (errno.EACCES,errno.EPERM)
for i,p in enumerate(PROTECTED):
 alias=BUILD+'/alias-'+str(i)
 try:
  os.symlink(p,alias)
  try:
   fd=os.open(alias,os.O_WRONLY);os.close(fd);r['symlink-'+str(i)]=False
  except OSError as e:r['symlink-'+str(i)]=e.errno in (errno.EACCES,errno.EPERM)
 finally:
  if os.path.lexists(alias):os.unlink(alias)
try:
 s=socket.socket();s.connect(('127.0.0.1',9));r['network']=False
except OSError as e:r['network']=e.errno in (errno.EACCES,errno.EPERM)
try:
 pid=os.fork()
 if pid==0:os._exit(0)
 os.waitpid(pid,0);r['fork_denied']=False
except OSError as e:r['fork_denied']=e.errno in (errno.EACCES,errno.EPERM)
try:
 pid=os.posix_spawn('/usr/bin/java',['/usr/bin/java','-version'],{})
 os.waitpid(pid,0);r['spawn_denied']=False
except OSError as e:r['spawn_denied']=e.errno in (errno.EACCES,errno.EPERM)
fd=os.open(SOURCE,os.O_WRONLY);os.close(fd);r['source_write_open']=True
p=BUILD+'/probe';open(p,'xb').write(b'allowed');os.unlink(p);r['build_write']=True
print(json.dumps(r,sort_keys=True))
raise SystemExit(0 if all(r.values()) else 1)
"""
    code = (
        "PROTECTED="
        + repr(protected)
        + "\nSOURCE="
        + repr(str(Path(request["destination"]) / request["proposal"]["edit"]["path"]))
        + "\nBUILD="
        + repr(request["outputs"] + "/classes")
        + "\n"
        + code
    )
    result = supervise(request, [sys.executable, "-I", "-B", "-c", code], "boundary-probe")
    if passed(result):
        bounded = dict(request, budget=dict(request["budget"], timeout_seconds=1))
        timeout = supervise(
            bounded,
            [sys.executable, "-I", "-B", "-c", "import time;time.sleep(10)"],
            "timeout-probe",
        )
        result["timeout_probe"] = timeout
        if not timeout["timeout"] or timeout["exit"] == 0:
            result["exit"] = 1
    return result


def apply(request):
    # The only replacement originates from the original package, not a patch translator.
    source = str(Path(request["destination"]) / request["proposal"]["edit"]["path"])
    code = """import os,hashlib
fd=os.open(PATH,os.O_RDWR|os.O_NOFOLLOW)
try:
 s=os.fstat(fd)
 assert s.st_nlink==1
 data=os.read(fd,262145)
 assert hashlib.sha256(data).hexdigest()==BASE
 os.lseek(fd,0,0)
 with os.fdopen(fd,'wb',closefd=False) as f:
  f.write(TEXT);f.truncate();f.flush();os.fsync(fd)
finally:os.close(fd)
"""
    code = (
        "PATH="
        + repr(source)
        + "\nBASE="
        + repr(
            request["proposal"]["handoff"]["snapshot"][request["proposal"]["edit"]["path"]][
                "sha256"
            ]
        )
        + "\nTEXT="
        + repr(request["proposal"]["edit"]["replacement"].encode())
        + "\n"
        + code
    )
    return supervise(request, [sys.executable, "-I", "-B", "-c", code], "apply")


def execute(admitted, runner=supervise, qualifier=probe, applier=apply):
    """Injected functions are unit-test doubles only; no CLI/environment override."""
    r = admitted["request"]
    out = Path(r["outputs"])
    gp = admitted["grant_path"]
    # Exclusive persistent reservation; no refund or retry, including failed probes.
    fd = os.open(str(gp) + ".used", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encoded({"request_sha256": identity(r), "reserved_at": time.time()}))
        f.flush()
        os.fsync(f.fileno())
    receipt = {
        "schema": "mana.exact-result/v1",
        "request_sha256": identity(r),
        "request_id": r["id"],
        "proposal_fingerprint": r["proposal"]["fingerprint"],
        "runtime": r["runtime"],
        "authorization": admitted["grant"],
        "human_approval": False,
        "provider_calls": 0,
        "status": "BLOCKED",
        "applied": False,
        "application_started": False,
        "steps": {},
        "initial": admitted["files"],
        "final": {},
        "stop_reason": None,
    }
    started = time.monotonic()
    try:
        (out / "classes").mkdir(mode=0o700)
        with (out / "control.json").open("x") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(identity(r) + "\n")
        result = qualifier(r)
        receipt["steps"]["boundary"] = result
        require(passed(result), "NATIVE_BOUNDARY_UNQUALIFIED")
        # Qualification must be per invocation, never loaded from an old receipt.
        for phase in ("baseline", "after") if r["operation"] == "repair-verify" else ("verify",):
            if phase == "after":
                require(
                    time.monotonic() - started
                    < r["budget"]["total_seconds"] - 3 * r["budget"]["timeout_seconds"],
                    "TOTAL_BUDGET_EXHAUSTED",
                )
                receipt["application_started"] = True
                result = applier(r)
                receipt["steps"]["apply"] = result
                receipt["applied"] = (
                    digest(read_file(Path(r["destination"]) / r["proposal"]["edit"]["path"]))
                    == r["result_sha256"]
                )
                require(
                    passed(result) and receipt["applied"], "APPLICATION_FAILED_PARTIAL_POSSIBLE"
                )
            for index, argv in enumerate(admitted["argv"]):
                require(
                    time.monotonic() - started
                    < r["budget"]["total_seconds"] - r["budget"]["timeout_seconds"],
                    "TOTAL_BUDGET_EXHAUSTED",
                )
                result = runner(r, argv, phase + "-" + str(index))
                receipt["steps"][phase + "-" + str(index)] = result
                # Baseline test may fail; compilation may not. No fixture rule in executor.
                require(
                    not result["timeout"] and not result["descendants_terminated"],
                    "VERIFICATION_TIMEOUT_OR_DESCENDANTS",
                )
                if phase == "baseline" and index == 1:
                    require(
                        result["exit"] == r["baseline"]["test_exit"]
                        and digest(result["stdout"].encode()) == r["baseline"]["stdout_sha256"],
                        "BASELINE_NOT_REPRODUCED",
                    )
                else:
                    require(result["exit"] == 0, "COMPILATION_OR_TEST_FAILED")
        receipt["status"] = "COMPLETE"
    except (Rejected, OSError, subprocess.SubprocessError) as e:
        receipt["stop_reason"] = str(e)
        receipt["status"] = "PARTIAL" if receipt["application_started"] else "BLOCKED"
    finally:
        try:
            for file in Path(r["destination"]).rglob("*"):
                require(not file.is_symlink(), "FINAL_SYMLINK")
                if not file.is_dir():
                    receipt["final"][str(file.relative_to(r["destination"]))] = digest(
                        read_file(file)
                    )
            expected = dict(admitted["files"])
            if receipt["applied"]:
                expected[r["proposal"]["edit"]["path"]] = r["result_sha256"]
            require(receipt["final"] == expected, "FINAL_CONTENT_MISMATCH")
        except (Rejected, OSError) as e:
            receipt["status"] = "PARTIAL"
            receipt["stop_reason"] = str(e)
        receipt["duration_ms"] = round((time.monotonic() - started) * 1000)
        data = encoded(receipt) + b"\n"
        artifact = "result.json"
        try:
            with (out / artifact).open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(data)
            artifact = "result.sha256"
            with (out / artifact).open("x") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(digest(data) + "\n")
        except OSError as e:
            # Effects and verifier observations survive a failed receipt, including close.
            # Do not retry, rewrite a partial receipt, or refund the reservation.
            receipt["receipt_error"] = {"artifact": artifact, "error": str(e)}
            if receipt["status"] == "COMPLETE":
                receipt["status"] = "PARTIAL" if receipt["application_started"] else "BLOCKED"
            if receipt["stop_reason"] is None:
                receipt["stop_reason"] = "RECEIPT_PERSISTENCE_FAILED"
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", choices=["repair", "verify"], required=True)
    parser.add_argument("--exact-request", required=True)
    parser.add_argument("--host-grant", required=True)
    parser.add_argument("--provider", choices=["none"], required=True)
    parser.add_argument(
        "--project-root"
    )  # public wrapper compatibility; must equal bound destination
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        r = load(safe_absolute(args.exact_request))
        require(
            r["operation"] == ("repair-verify" if args.entry == "repair" else "verify"),
            "ENTRY_OPERATION_MISMATCH",
        )
        require(
            args.project_root is None or args.project_root == r["destination"],
            "PROJECT_ROOT_MISMATCH",
        )
        admitted = validate(r, safe_absolute(args.host_grant), runtime())
        result = execute(admitted)
    except (Rejected, OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as e:
        result = {
            "schema": "mana.exact-result/v1",
            "status": "BLOCKED",
            "stop_reason": str(e),
            "application_started": False,
            "applied": False,
            "provider_calls": 0,
        }
    print(json.dumps(result, sort_keys=True))
    if "receipt_error" in result:
        error = result["receipt_error"]
        print(
            f"RECEIPT_PERSISTENCE_FAILED: {error['artifact']}: {error['error']}; "
            f"status={result['status']}, application_started={result['application_started']}, "
            f"applied={result['applied']}; stop_reason={result['stop_reason']}",
            file=sys.stderr,
        )
    return 0 if result["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
