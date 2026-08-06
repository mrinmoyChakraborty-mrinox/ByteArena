import os
import shutil
import sys

# Language config table. Add a language by adding an entry here — no new code paths.
#
#   extension:         source file extension
#   source_name:       fixed filename the source is copied to in the scratch dir
#   compile:           compile command (list form) or None for interpreted languages
#   run:               run command (list form); {src}/{bin}/{dir} get substituted
#   compile_timeout_ms: hard cap on the compile step; 0 = no explicit cap

LANGUAGES = {
    "python": {
        "extension": "py",
        "source_name": "main.py",
        "compile": [sys.executable, "-m", "py_compile", "{src}"],
        "run": [sys.executable, "{src}"],
        "compile_timeout_ms": 10000,
    },
    "cpp": {
        "extension": "cpp",
        "source_name": "main.cpp",
        "compile": ["g++", "-O2", "-std=c++17", "-o", "{bin}", "{src}"],
        "run": ["{bin}"],
        "compile_timeout_ms": 15000,
    },
}

_COMPILER_DIRS = set()


def _register_compiler_dirs():
    for lang, cfg in LANGUAGES.items():
        if not cfg["compile"]:
            continue
        compiler = cfg["compile"][0]
        resolved = shutil.which(compiler)
        if resolved:
            _COMPILER_DIRS.add(os.path.dirname(resolved))


_register_compiler_dirs()


def source_name_for(lang: str) -> str:
    return LANGUAGES[lang]["source_name"]


def binary_name_for(lang: str) -> str:
    if os.name == "nt":
        return "main.exe"
    return "main.out"


def format_cmd(tokens, **kwargs) -> list:
    return [t.format(**kwargs) for t in tokens]


def run_env_for(lang: str) -> dict:
    """Environment for the run step.

    C/C++ binaries produced by MSYS2/mingw need the compiler's bin dir on PATH
    to locate their DLLs (libstdc++-6.dll, etc.) at runtime.
    """
    env = dict(os.environ)
    if _COMPILER_DIRS:
        extra = os.pathsep.join(sorted(_COMPILER_DIRS))
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env
