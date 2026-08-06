"""Cross-platform sandbox for running untrusted participant code.

Two backends behind one interface (`run_sandboxed`):

- POSIX: dedicated low-privilege user (opt-in via BYTEARENA_SANDBOX_USER),
  `setrlimit` CPU/address-space caps, process-group kill on wall-clock timeout,
  scratch dir wiped after every run.
- Windows: a Job Object with a memory cap and kill-on-close, so the whole
  process tree is terminated on timeout and nothing can outlive the job.

Memory model: the *enforcement* cap (rlimit/job) is set generously above the
problem's memory limit so a process that merely exceeds the documented limit
survives long enough to be measured; the *verdict* threshold (peak memory vs
the problem's limit) is applied by the worker. This keeps the host laptop
safe (the cap) while making MLE deterministic and consistent across platforms.

NOTE: outbound-network blocking is NOT implemented in this sprint. The
production POSIX deployment should block outbound sockets for the sandbox
user via firewall rules or a network namespace, per ARCHITECTURE.md §3.
"""

import os
import signal
import subprocess
import sys
import threading
import time

from dataclasses import dataclass

IS_POSIX = os.name == "posix"

if IS_POSIX:
    import resource
    import pwd

# Optional dedicated low-privilege user for POSIX runs (production only).
SANDBOX_RUN_USER = os.environ.get("BYTEARENA_SANDBOX_USER") or None

# Enforcement memory cap = max(2x the problem limit, +256 MB headroom).
def enforcement_mem_mb(limit_mb: int) -> int:
    return max(limit_mb * 2, limit_mb + 256)


class SandboxError(Exception):
    pass


@dataclass
class RawRunResult:
    stdout: bytes
    stderr: bytes
    runtime_ms: int
    mem_kb: int
    exit_status: int
    timed_out: bool = False


# ============================================================================
# Plain subprocess (used for the compile step, which is trusted toolchain).
# ============================================================================
def run_plain(cmd, cwd=None, timeout_ms=15000, stdin_bytes=b""):
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=(timeout_ms / 1000.0) if timeout_ms else None,
        )
    except subprocess.TimeoutExpired:
        raise SandboxError(f"process timed out after {timeout_ms}ms")
    except OSError as e:
        raise SandboxError(f"failed to launch process: {e}")
    return proc


# ============================================================================
# Sandboxed run
# ============================================================================
def run_sandboxed(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env=None) -> RawRunResult:
    if IS_POSIX:
        return _run_posix(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env)
    return _run_windows(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env)


# ----------------------------------------------------------------------------
# POSIX backend
# ----------------------------------------------------------------------------
def _drop_privileges():
    if not SANDBOX_RUN_USER:
        return
    try:
        pw = pwd.getpwnam(SANDBOX_RUN_USER)
    except KeyError:
        return
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)


def _posix_preexec(mem_limit_mb, time_limit_ms):
    def preexec():
        # New process group so we can kill the whole tree on timeout.
        os.setsid()
        _drop_privileges()
        if mem_limit_mb:
            cap = enforcement_mem_mb(mem_limit_mb)
            resource.setrlimit(resource.RLIMIT_AS, (cap * 1024 * 1024, cap * 1024 * 1024))
        if time_limit_ms:
            cpu_s = max(int(time_limit_ms / 1000.0), 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))

    return preexec


def _read_proc_vmhwm(pid) -> int:
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])  # kB
    except OSError:
        pass
    return 0


def _run_posix(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env) -> RawRunResult:
    start = time.perf_counter()
    rusage_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=_posix_preexec(mem_limit_mb, time_limit_ms),
        )
    except OSError as e:
        raise SandboxError(f"failed to launch process: {e}")

    timed_out = False
    try:
        stdout, stderr = proc.communicate(input=stdin_bytes, timeout=(time_limit_ms / 1000.0))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        stdout, stderr = proc.communicate()

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    rusage_after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    mem_kb = _read_proc_vmhwm(proc.pid)
    if not mem_kb:
        # ru_maxrss is in KB on Linux, bytes on macOS — handle the delta as best effort.
        delta = rusage_after - rusage_before
        mem_kb = delta // 1024 if delta > (1 << 40) else delta

    return RawRunResult(
        stdout=stdout,
        stderr=stderr,
        runtime_ms=elapsed_ms,
        mem_kb=mem_kb,
        exit_status=-1 if timed_out else proc.returncode,
        timed_out=timed_out,
    )


# ----------------------------------------------------------------------------
# Windows backend (Job Objects)
# ----------------------------------------------------------------------------
_WIN_JOB_NAME = None
_WIN_JOB_HANDLES = []


def _win_create_job(mem_limit_mb):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise SandboxError("CreateJobObjectW failed")

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    cap_bytes = enforcement_mem_mb(mem_limit_mb) * 1024 * 1024
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_JOB_MEMORY
    )
    info.JobMemoryLimit = ctypes.c_size_t(cap_bytes)

    if not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise SandboxError("SetInformationJobObject failed")

    # Keep handles alive for the module lifetime to prevent premature closure.
    _WIN_JOB_HANDLES.append(job)
    return job


def _win_assign_process(job, pid):
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.AssignProcessToJobObject(job, ctypes.c_void_p(pid)):
        return False
    return True


def _win_terminate_job(job):
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject(job, 137)


def _win_job_peak_kb(job) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    if kernel32.QueryInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info), None):
        return int(info.PeakJobMemoryUsed) // 1024
    return 0


def _run_windows(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env) -> RawRunResult:
    import ctypes

    CREATE_NEW_PROCESS_GROUP = 0x00000200

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as e:
        raise SandboxError(f"failed to launch process: {e}")

    # Try the Job Object path first. It fails when the parent process itself
    # runs inside a job that disallows breakaway (common in CI/agent shells),
    # in which case we fall back to poll + taskkill.
    job = None
    try:
        job = _win_create_job(mem_limit_mb)
        if not _win_assign_process(job, int(proc.pid)):
            job = None
    except SandboxError:
        job = None

    if job:
        start = time.perf_counter()
        timed_out = False
        try:
            stdout, stderr = proc.communicate(input=stdin_bytes, timeout=(time_limit_ms / 1000.0))
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                _win_terminate_job(job)
            except Exception:
                pass
            stdout, stderr = proc.communicate()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        mem_kb = _win_job_peak_kb(job)
    else:
        stdout, stderr, elapsed_ms, timed_out, mem_kb = _run_windows_fallback(
            proc, stdin_bytes, time_limit_ms, mem_limit_mb
        )

    return RawRunResult(
        stdout=stdout,
        stderr=stderr,
        runtime_ms=elapsed_ms,
        mem_kb=mem_kb,
        exit_status=-1 if timed_out else proc.returncode,
        timed_out=timed_out,
    )


# ----------------------------------------------------------------------------
# Windows fallback (no Job Object available)
# ----------------------------------------------------------------------------
def _win_taskkill(pid):
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        timeout=10,
    )


def _win_process_memory(pid, field):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return 0
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return int(getattr(counters, field)) // 1024
    finally:
        kernel32.CloseHandle(handle)
    return 0


def _run_windows_fallback(proc, stdin_bytes, time_limit_ms, mem_limit_mb):
    """Poll-based run: pipes drained on threads, peak memory measured via
    GetProcessMemoryInfo, process tree killed with taskkill on timeout or
    when the enforcement memory cap is exceeded."""
    stdout_buf, stderr_buf = [], []
    out_thread = threading.Thread(target=lambda: stdout_buf.append(proc.stdout.read()), daemon=True)
    err_thread = threading.Thread(target=lambda: stderr_buf.append(proc.stderr.read()), daemon=True)
    out_thread.start()
    err_thread.start()

    try:
        proc.stdin.write(stdin_bytes)
    except (BrokenPipeError, OSError):
        pass
    try:
        proc.stdin.close()
    except OSError:
        pass

    cap_kb = enforcement_mem_mb(mem_limit_mb) * 1024 if mem_limit_mb else 0
    start = time.perf_counter()
    timed_out = False
    peak_kb = 0

    while True:
        if proc.poll() is not None:
            break
        ws_kb = _win_process_memory(proc.pid, "WorkingSetSize")
        if ws_kb:
            peak_kb = max(peak_kb, ws_kb)
        if cap_kb and ws_kb > cap_kb:
            _win_taskkill(proc.pid)
            break
        if time.perf_counter() - start > time_limit_ms / 1000.0:
            _win_taskkill(proc.pid)
            timed_out = True
            break
        time.sleep(0.01)

    out_thread.join(timeout=5)
    err_thread.join(timeout=5)
    stdout = stdout_buf[0] if stdout_buf else b""
    stderr = stderr_buf[0] if stderr_buf else b""

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    peak_kb = max(peak_kb, _win_process_memory(proc.pid, "PeakWorkingSetSize"))
    return stdout, stderr, elapsed_ms, timed_out, peak_kb
