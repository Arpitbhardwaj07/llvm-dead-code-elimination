"""
Flask Web Application Server
=============================
Provides a clean, thin HTTP interface for the DCE Optimizer and Phases Viewer:
- GET  /              : Renders index.html
- GET  /api/examples  : Returns pre-configured C code examples
- POST /api/optimize  : Compiles C to IR, runs DCE pass, returns before/after & stats
- POST /api/phases    : Extracts all 5 compiler pipeline stages
- GET  /api/status    : Returns Clang presence and version information
"""

import sys
import os
from flask import Flask, render_template, request, jsonify

from compiler import compile_to_ir, get_all_compiler_phases, get_clang_version
from dce import run_dce
from examples import get_examples

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """Serves the single-page application frontend."""
    return render_template("index.html")


@app.route("/api/examples", methods=["GET"])
def api_examples():
    """Returns the list of sample C programs."""
    try:
        return jsonify(get_examples())
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to load examples: {str(e)}"}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    """Checks and returns the status of the Clang compiler toolchain."""
    try:
        available, info = get_clang_version()
        return jsonify({
            "ok": True,
            "clang_available": available,
            "clang_version": info
        })
    except Exception as e:
        return jsonify({
            "ok": True,
            "clang_available": False,
            "clang_version": str(e)
        })


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    """
    Compiles user C code (or accepts direct LLVM IR) and applies the DCE pass.
    Expected JSON body: {"code": "<code string>", "input_type": "c"|"ir"}
    Returns:
        {"ok": true, "before_ir": str, "after_ir": str, "removed": list, "rounds": list, "stats": dict}
    """
    try:
        data = request.get_json(force=True, silent=True)
        if not data or "code" not in data:
            return jsonify({
                "ok": False,
                "error": "Invalid request body. Expected JSON with 'code' key.",
                "details": ""
            }), 400

        user_code = data["code"]
        input_type = data.get("input_type", "c").lower()

        if input_type == "ir":
            # Direct LLVM IR input mode
            if not user_code or not user_code.strip():
                return jsonify({
                    "ok": False,
                    "error": "LLVM IR input is empty. Please paste valid LLVM IR text.",
                    "details": ""
                }), 400

            before_ir = user_code
            dce_res = run_dce(before_ir)
            return jsonify({
                "ok": True,
                "before_ir": before_ir,
                "after_ir": dce_res["after_ir"],
                "removed": dce_res["removed"],
                "rounds": dce_res["rounds"],
                "stats": dce_res["stats"]
            })

        # Default: C source code mode (Compile to unoptimized LLVM IR via Clang)
        ir_res = compile_to_ir(user_code)
        if not ir_res.get("ok"):
            return jsonify({
                "ok": False,
                "error": ir_res.get("error", "Compilation failed"),
                "details": ir_res.get("details", "")
            }), 400

        before_ir = ir_res["ir"]

        # Steps 2-4: Run DCE Pass
        dce_res = run_dce(before_ir)

        # Step 5: Return result
        return jsonify({
            "ok": True,
            "before_ir": before_ir,
            "after_ir": dce_res["after_ir"],
            "removed": dce_res["removed"],
            "rounds": dce_res["rounds"],
            "stats": dce_res["stats"]
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "Unexpected server error during optimization",
            "details": str(e)
        }), 500


@app.route("/api/phases", methods=["POST"])
def api_phases():
    """
    Returns output for compiler phases:
    Tokens -> AST -> LLVM IR Before -> LLVM IR After -> Assembly.
    Expected JSON body: {"code": "<code string>", "input_type": "c"|"ir"}
    """
    try:
        data = request.get_json(force=True, silent=True)
        if not data or "code" not in data:
            return jsonify({
                "ok": False,
                "error": "Invalid request body. Expected JSON with 'code' key.",
                "details": ""
            }), 400

        user_code = data["code"]
        input_type = data.get("input_type", "c").lower()

        if input_type == "ir":
            # For direct IR input, tokens and AST are not applicable
            dce_res = run_dce(user_code)
            return jsonify({
                "ok": True,
                "phases": {
                    "tokens": {"ok": True, "content": "[Lexical Tokens: N/A for raw LLVM IR input]"},
                    "ast": {"ok": True, "content": "[Syntax Tree: N/A for raw LLVM IR input]"},
                    "ir_before": {"ok": True, "content": user_code},
                    "ir_after": {"ok": True, "content": dce_res["after_ir"], "dce_data": dce_res},
                    "assembly": {"ok": True, "content": "[Target Assembly: run from C source or invoke Clang with .ll]"}
                }
            })

        res = get_all_compiler_phases(user_code)
        if not res.get("ok"):
            return jsonify({
                "ok": False,
                "error": res.get("error", "Phase extraction failed"),
                "details": res.get("details", "")
            }), 400

        return jsonify(res)

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "Unexpected server error during phase extraction",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    # College review mode: Localhost 127.0.0.1 on port 5000
    print("Starting LLVM Dead Code Elimination server on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)

