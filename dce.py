"""
Dead Code Elimination (DCE) Optimization Pass
==============================================
Project: Simple LLVM Dead Code Elimination Pass
Domain : Compiler Design (Review-2 Working Model)

Theoretical Workflow (Matching Review-1 Slides):
------------------------------------------------
Step 1: Compile C code to unoptimized LLVM IR using Clang (-O0).
Step 2: Parse the LLVM IR and traverse each instruction in each basic block.
Step 3: Check whether each instruction's result is used anywhere in the function.
Step 4: Safely erase instructions with zero uses and no side effects.
Step 5: Output the optimized LLVM IR for verification (repeat until fixed-point).
"""

import re
from typing import Dict, List, Set, Any


# Pure opcodes that are safe to remove when their result is never used.
# These operations do NOT modify memory, I/O, or control flow.
SAFE_OPCODES = {
    "add", "sub", "mul",
    "fadd", "fsub", "fmul",
    "and", "or", "xor", "shl", "lshr", "ashr",
    "icmp", "fcmp",
    "zext", "sext", "trunc", "bitcast",
    "sitofp", "uitofp", "fptosi", "fptoui",
    "getelementptr", "select", "phi",
}

# Safety note for viva:
# 1. Division (sdiv, udiv, fdiv) is NOT removed because division by zero
#    causes CPU hardware traps; removing it could mask an intentional error.
# 2. Calls, stores, returns, and branches are NEVER removed because they
#    have side effects (I/O, memory writes, control flow).


def is_var_used(var_name: str, line: str) -> bool:
    """Check if var_name (%var) is used as an operand in an instruction line."""
    # Ensure %a does not accidentally match %a_1 or %abc
    pattern = r"(?<![a-zA-Z0-9_.])" + re.escape(var_name) + r"(?![a-zA-Z0-9_.])"
    return re.search(pattern, line) is not None


def parse_definition(line: str):
    """
    Check if a line defines a value (%var = opcode ...).
    Returns (var_name, opcode) or ("", "") if not a definition.
    """
    stripped = line.strip()
    match = re.match(r"^(%[a-zA-Z0-9_.\"]+)\s*=\s*(?:tail\s+|musttail\s+|notail\s+)?([a-zA-Z0-9_-]+)\b", stripped)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def is_write_only_alloca(var_name: str, instructions: List[dict]) -> tuple:
    """
    Rule C (Slide 4 - Unused stack variables):
    If a variable %p is only ever written to by 'store ... ptr %p' and NEVER
    loaded or passed anywhere, both %p and its stores are completely dead.
    """
    associated_stores = []
    for inst in instructions:
        if inst["var"] == var_name:
            continue
        if not is_var_used(var_name, inst["text"]):
            continue

        text = inst["text"].strip()
        lower = text.lower()

        # Must be a pure store where %p is strictly the destination pointer
        if not text.startswith("store ") or "volatile" in lower or "@" in text or "," not in text:
            return False, []

        val_part, dest_part = text.split(",", 1)
        # If %p appears in the stored value, it escapes!
        if is_var_used(var_name, val_part):
            return False, []
        if not is_var_used(var_name, dest_part):
            return False, []

        associated_stores.append(inst)

    return True, associated_stores


def optimize_function(func_name: str, func_lines: List[dict]):
    """
    Runs DCE on one function until a fixed point is reached (convergence).
    Why loop? Deleting an instruction can reduce uses of other instructions
    to zero, triggering a cascade of removals until nothing changes.
    """
    current = list(func_lines)
    all_removed = []
    rounds = []
    round_no = 1

    while True:
        round_removed = []
        instructions = [x for x in current if x["is_instruction"]]

        # Step 3: Count how many times each defined variable is used
        use_counts = {}
        for inst in instructions:
            if inst["var"]:
                count = sum(1 for other in instructions if other is not inst and is_var_used(inst["var"], other["text"]))
                use_counts[inst["var"]] = count

        to_delete_line_nos = set()

        # Step 4: Dead instruction rule (zero uses and safe opcode)
        for inst in instructions:
            var = inst["var"]
            opcode = inst["opcode"]
            if var and use_counts.get(var, 0) == 0:
                is_dead = False
                if opcode in SAFE_OPCODES:
                    is_dead = True
                elif opcode == "load" and "volatile" not in inst["text"].lower() and "atomic" not in inst["text"].lower():
                    is_dead = True

                if is_dead:
                    to_delete_line_nos.add(inst["line_no"])
                    round_removed.append({
                        "function": func_name,
                        "block": inst["block"],
                        "line_no": inst["line_no"],
                        "text": inst["text"].strip(),
                        "reason": f"result {var} is never used",
                        "round": round_no
                    })

        # Step 4 (Rule C): Write-only alloca rule
        for inst in instructions:
            if inst["opcode"] == "alloca" and inst["line_no"] not in to_delete_line_nos:
                is_wo, stores = is_write_only_alloca(inst["var"], instructions)
                if is_wo:
                    to_delete_line_nos.add(inst["line_no"])
                    round_removed.append({
                        "function": func_name,
                        "block": inst["block"],
                        "line_no": inst["line_no"],
                        "text": inst["text"].strip(),
                        "reason": f"variable {inst['var']} is written but never read",
                        "round": round_no
                    })
                    for s in stores:
                        if s["line_no"] not in to_delete_line_nos:
                            to_delete_line_nos.add(s["line_no"])
                            round_removed.append({
                                "function": func_name,
                                "block": s["block"],
                                "line_no": s["line_no"],
                                "text": s["text"].strip(),
                                "reason": f"variable {inst['var']} is written but never read",
                                "round": round_no
                            })

        # Record this round
        rounds.append({"round": round_no, "removed": len(round_removed)})

        # If round removed 0 instructions, we reached fixed point!
        if not round_removed:
            break

        all_removed.extend(round_removed)
        current = [x for x in current if x["line_no"] not in to_delete_line_nos]
        round_no += 1

    return current, all_removed, rounds


def run_dce(ir_text: str) -> Dict[str, Any]:
    """
    Main entry point for Dead Code Elimination.
    Parses LLVM IR, applies DCE per function, and outputs optimized IR with stats.
    """
    if not ir_text or not ir_text.strip():
        return {
            "after_ir": ir_text or "",
            "removed": [],
            "rounds": [{"round": 1, "removed": 0}],
            "stats": {"before": 0, "after": 0, "removed": 0, "percent": 0.0, "per_function": []}
        }

    raw_lines = ir_text.splitlines()
    all_lines = []
    func_map = {}
    func_order = []

    in_func = False
    cur_func = ""
    cur_block = ""

    # Step 2: Parse IR into basic blocks and instructions
    for idx, raw in enumerate(raw_lines):
        line_no = idx + 1
        stripped = raw.strip()

        if stripped.startswith("define ") and "{" in stripped:
            in_func = True
            name_match = re.search(r"(@[a-zA-Z0-9_.\"]+)", stripped)
            cur_func = name_match.group(1) if name_match else f"@func_{line_no}"
            cur_block = "entry"
            func_map[cur_func] = []
            func_order.append(cur_func)
            all_lines.append({"line_no": line_no, "text": raw, "is_func": True, "func": cur_func})
            continue

        if in_func and stripped == "}":
            in_func = False
            all_lines.append({"line_no": line_no, "text": raw, "is_func": True, "func": cur_func})
            cur_func = ""
            cur_block = ""
            continue

        if in_func:
            # Check for block label (e.g., entry:, for.body:)
            lbl_match = re.match(r"^([a-zA-Z0-9_.\"]+):(?:\s*;.*)?$", stripped)
            if lbl_match:
                cur_block = lbl_match.group(1).strip('"')
                item = {"line_no": line_no, "text": raw, "block": cur_block, "is_instruction": False, "var": "", "opcode": "", "func": cur_func}
            else:
                var, opcode = parse_definition(raw)
                is_instr = bool(stripped and not stripped.startswith(";"))
                item = {"line_no": line_no, "text": raw, "block": cur_block, "is_instruction": is_instr, "var": var, "opcode": opcode, "func": cur_func}

            func_map[cur_func].append(item)
            all_lines.append(item)
        else:
            all_lines.append({"line_no": line_no, "text": raw, "is_instruction": False})

    if not func_order:
        return {
            "after_ir": ir_text,
            "removed": [],
            "rounds": [{"round": 1, "removed": 0}],
            "stats": {"before": 0, "after": 0, "removed": 0, "percent": 0.0, "per_function": []}
        }

    # Run DCE on each function
    all_removed = []
    per_function = []
    total_before = 0
    total_removed = 0
    merged_rounds = {}
    max_round = 1

    for fname in func_order:
        flines = func_map[fname]
        f_before = sum(1 for x in flines if x["is_instruction"])
        total_before += f_before

        opt_lines, f_rem, f_rounds = optimize_function(fname, flines)
        f_after = sum(1 for x in opt_lines if x["is_instruction"])
        total_removed += (f_before - f_after)

        per_function.append({"name": fname, "before": f_before, "after": f_after})
        all_removed.extend(f_rem)

        for r in f_rounds:
            merged_rounds[r["round"]] = merged_rounds.get(r["round"], 0) + r["removed"]
            if r["round"] > max_round:
                max_round = r["round"]

    rounds_summary = [{"round": r, "removed": merged_rounds.get(r, 0)} for r in range(1, max_round + 1)]
    if not rounds_summary or rounds_summary[-1]["removed"] != 0:
        rounds_summary.append({"round": len(rounds_summary) + 1, "removed": 0})

    # Step 5: Reconstruct optimized LLVM IR output
    all_removed.sort(key=lambda x: x["line_no"])
    removed_ids = {x["line_no"] for x in all_removed}
    after_lines = [l["text"] for l in all_lines if l["line_no"] not in removed_ids]
    after_ir = "\n".join(after_lines) + ("\n" if ir_text.endswith("\n") else "")

    percent = round((total_removed / total_before * 100), 1) if total_before > 0 else 0.0

    return {
        "after_ir": after_ir,
        "removed": all_removed,
        "rounds": rounds_summary,
        "stats": {
            "before": total_before,
            "after": total_before - total_removed,
            "removed": total_removed,
            "percent": percent,
            "per_function": per_function
        }
    }
