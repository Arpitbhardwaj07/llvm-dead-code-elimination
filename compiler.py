"""
Compiler Interface for Clang Subprocess Operations
===================================================
Project: Simple LLVM Dead Code Elimination Pass
Domain : Compiler Design (Review-2 Working Model)

Maps directly to Slide 6 & 7:
- Step 1: Compiles C source to unoptimized LLVM IR using Clang.
- Slide 7: Extracts the 5 compiler phases:
  1. Lexical Analysis (Tokens)
  2. Syntax Analysis (AST)
  3. Intermediate Code (LLVM IR Before)
  4. Code Optimization (LLVM IR After via our DCE pass)
  5. Target Code Generation (Target Machine Assembly)
"""

import os
import shutil
import subprocess
import tempfile
from typing import Dict, Any, Optional, Tuple

from dce import run_dce

# Timeout for any clang command (in seconds)
TIMEOUT = 10


def find_clang() -> Optional[str]:
    """Finds clang binary on PATH or standard Windows installation path."""
    env_path = os.environ.get("CLANG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    
    found = shutil.which("clang")
    if found:
        return found

    for p in [r"C:\Program Files\LLVM\bin\clang.exe", r"C:\Program Files (x86)\LLVM\bin\clang.exe"]:
        if os.path.isfile(p):
            return p
    return None


def get_clang_version() -> Tuple[bool, str]:
    """Returns (True, version_string) or (False, error_message)."""
    clang = find_clang()
    if not clang:
        return False, "Clang was not found on PATH or CLANG_PATH."
    try:
        proc = subprocess.run([clang, "--version"], capture_output=True, text=True, timeout=TIMEOUT)
        first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
        return True, first_line.strip()
    except Exception as e:
        return False, str(e)


def compile_to_ir(c_code: str) -> Dict[str, Any]:
    """
    Step 1: Compiles C code into unoptimized LLVM IR using Clang.
    
    Why these flags?
    - -S -emit-llvm: Emits human-readable LLVM IR text instead of binary.
    - -O0: Keeps Clang from performing optimizations itself, so dead code stays for us to find.
    - -Xclang -disable-O0-optnone: Allows downstream optimization passes to run on functions.
    - -fno-discard-value-names: Preserves human-readable variable names like %sum.
    """
    if not c_code or not c_code.strip():
        return {"ok": False, "error": "C code is empty. Please enter C source code."}
    if len(c_code.encode("utf-8")) > 20 * 1024:
        return {"ok": False, "error": "Input code exceeds 20 KB limit."}

    clang = find_clang()
    if not clang:
        return {"ok": False, "error": "Clang was not found. Please verify LLVM is installed."}

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "input.c")
        out_ll = os.path.join(tmpdir, "output.ll")

        with open(src, "w", encoding="utf-8") as f:
            f.write(c_code)

        cmd = [
            clang,
            "-S", "-emit-llvm",
            "-O0",
            "-Xclang", "-disable-O0-optnone",
            "-fno-discard-value-names",
            src, "-o", out_ll
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "error": "Syntax/Semantic error reported by the Clang frontend",
                    "details": proc.stderr.strip()
                }
            with open(out_ll, "r", encoding="utf-8", errors="replace") as f:
                ir_text = f.read()
            return {"ok": True, "ir": ir_text}
        except Exception as e:
            return {"ok": False, "error": f"Failed to execute Clang: {str(e)}"}


def get_all_compiler_phases(c_code: str) -> Dict[str, Any]:
    """
    Slide 7: Extracts all compiler phases independently:
    Tokens -> AST -> LLVM IR Before -> LLVM IR After -> Assembly.
    """
    clang = find_clang()
    if not clang:
        return {"ok": False, "error": "Clang compiler was not found."}

    phases = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "input.c")
        with open(src, "w", encoding="utf-8") as f:
            f.write(c_code)

        # 1. Lexical Analysis (Tokens): clang -dump-tokens
        try:
            p_tok = subprocess.run([clang, "-fsyntax-only", "-Xclang", "-dump-tokens", src], capture_output=True, text=True, timeout=TIMEOUT)
            tok_out = p_tok.stderr if p_tok.stderr else p_tok.stdout
            phases["tokens"] = {"ok": True, "content": tok_out}
        except Exception as e:
            phases["tokens"] = {"ok": False, "content": str(e)}

        # 2. Syntax Analysis (AST): clang -ast-dump
        try:
            p_ast = subprocess.run([clang, "-fsyntax-only", "-Xclang", "-ast-dump", "-fno-color-diagnostics", src], capture_output=True, text=True, timeout=TIMEOUT)
            phases["ast"] = {"ok": p_ast.returncode == 0, "content": p_ast.stdout if p_ast.returncode == 0 else p_ast.stderr}
        except Exception as e:
            phases["ast"] = {"ok": False, "content": str(e)}

        # 3. Intermediate Code Generation (LLVM IR Before)
        ir_res = compile_to_ir(c_code)
        if ir_res["ok"]:
            before_ir = ir_res["ir"]
            phases["ir_before"] = {"ok": True, "content": before_ir}

            # 4. Code Optimization (LLVM IR After via our custom DCE pass)
            dce_res = run_dce(before_ir)
            after_ir = dce_res["after_ir"]
            phases["ir_after"] = {"ok": True, "content": after_ir, "dce_data": dce_res}

            # 5. Target Code Generation (Machine Assembly from optimized IR)
            opt_ll = os.path.join(tmpdir, "opt.ll")
            asm_file = os.path.join(tmpdir, "out.s")
            with open(opt_ll, "w", encoding="utf-8") as f:
                f.write(after_ir)

            try:
                p_asm = subprocess.run([clang, "-S", opt_ll, "-o", asm_file], capture_output=True, text=True, timeout=TIMEOUT)
                if p_asm.returncode == 0 and os.path.exists(asm_file):
                    with open(asm_file, "r", encoding="utf-8", errors="replace") as f:
                        phases["assembly"] = {"ok": True, "content": f.read()}
                else:
                    phases["assembly"] = {"ok": False, "content": p_asm.stderr}
            except Exception as e:
                phases["assembly"] = {"ok": False, "content": str(e)}
        else:
            phases["ir_before"] = {"ok": False, "content": ir_res.get("details", "")}
            phases["ir_after"] = {"ok": False, "content": "Skipped (IR generation failed)"}
            phases["assembly"] = {"ok": False, "content": "Skipped (IR generation failed)"}

    return {"ok": True, "phases": phases}
