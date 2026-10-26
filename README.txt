================================================================================
LLVM DEAD CODE ELIMINATION (DCE) OPTIMIZATION PASS
College Compiler Design Project (Review-2 Working Model)
================================================================================

HONEST SCOPE NOTE:
This Dead Code Elimination pass is implemented in Python and operates on LLVM
IR text. It is NOT a C++ LLVM compiler plugin. However, the algorithm strictly
replicates the theoretical logic and pipeline of a standard function-level LLVM
DCE pass.

--------------------------------------------------------------------------------
1. SETUP & EXECUTION INSTRUCTIONS
--------------------------------------------------------------------------------

Prerequisites:
- Windows OS with PowerShell
- Python 3.10+ (configured with project-local virtual environment)
- LLVM / Clang 15+ (with opaque pointers support) on PATH or set in CLANG_PATH

Step 1: Create and activate virtual environment
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

Step 2: Install dependencies
    python -m pip install -r requirements.txt

Step 3: Run the web application
    python app.py
    Open your browser and navigate to: http://127.0.0.1:5000

Step 4: Run automated test suites
    python -m unittest discover tests -v

--------------------------------------------------------------------------------
2. THE DCE ALGORITHM IN 5 PLAIN SENTENCES
--------------------------------------------------------------------------------
1. The optimizer isolates each function body and partitions instructions across
   basic blocks.
2. It constructs def-use counts by counting how many other instruction lines
   reference each defined SSA register as an operand.
3. Any instruction producing a result with zero uses that belongs to the safe
   pure-operation set (such as arithmetic, logic, or pure loads) is eliminated.
4. Any stack allocation (alloca) that is only ever written to by stores and
   never read or passed elsewhere is eliminated along with its stores.
5. Because deleting an instruction reduces the use counts of its input operands,
   the process repeats in successive rounds until a round removes zero
   instructions (reaching a fixed point).

--------------------------------------------------------------------------------
3. LIMITATIONS
--------------------------------------------------------------------------------
1. Text-based IR analysis: Operates on textual LLVM IR using Python instead of
   in-memory LLVM C++ PassManager data structures.
2. Conservative safety on division: Instructions such as sdiv, udiv, fdiv, and
   remainder operations are deliberately preserved even when unused, because
   division by zero triggers hardware exceptions/traps.
3. Function-level scope: Operates strictly within single function boundaries; it
   does not perform inter-procedural optimization or global memory alias analysis.

--------------------------------------------------------------------------------
4. TEAM MEMBER ROLES & DETAILS (MATCHING SLIDE 2)
--------------------------------------------------------------------------------
- Abhishek Padhy  (24BCB0116) : Clang compiler interface and pipeline extraction
                                (compiler.py, test_compiler.py)
- Arpit Bhardwaj   (24BCI0036) : Core DCE algorithm and fixed-point cascade engine
                                (dce.py, test_dce.py)
- Kushagra Kumar   (24BKT0019) : Flask backend, UI dashboard, sample programs,
                                and documentation (app.py, templates/index.html,
                                examples.py, README.txt)

--------------------------------------------------------------------------------
5. VIVA CHEAT SHEET (8 ESSENTIAL QUESTIONS & ANSWERS)
--------------------------------------------------------------------------------

Q1: What is Intermediate Representation (IR) and why do compilers use it?
A1: IR is a machine-independent, low-level language that sits between the
    high-level source code (C) and the target machine assembly (x86/ARM).
    It allows compilers to perform optimizations once on the IR rather than
    re-implementing them for every target hardware architecture.

Q2: Why do we compile with -O0 -Xclang -disable-O0-optnone?
A2: By default, Clang at -O0 adds an 'optnone' attribute to functions to prevent
    downstream passes from modifying them. Passing -disable-O0-optnone and -O0
    instructs Clang to leave our dead statements unoptimized without blocking
    subsequent custom optimization passes.

Q3: Why must the DCE algorithm loop until nothing changes (fixed-point)?
A3: In a dependency chain like `a = x + 1; b = a * 2;`, initially `a` has 1 use
    so it cannot be deleted. Once Round 1 deletes `b` (0 uses), `a` now has 0
    uses in Round 2. We loop until a round removes 0 instructions, proving that
    all cascading dead dependencies are fully purged.

Q4: Why are function call instructions (call/invoke) never removed?
A4: Function calls may have external side effects (e.g., printing to screen,
    writing to files, modifying global state, or halting execution). Removing
    a call would alter observable program behavior, violating compiler safety.

Q5: Why is integer/floating-point division kept even if its result is unused?
A5: Division by zero triggers a CPU hardware exception (SIGFPE). If an unused
    division evaluated to division by zero, deleting it would suppress an
    intentional or observable crash, subtly changing program behavior.

Q6: What is a Basic Block in compiler theory?
A6: A basic block is a straight-line sequence of instructions with a single
    entry (at the start) and a single exit (at the terminal branch or return),
    with no internal branching into or out of the middle.

Q7: How does Static Single Assignment (SSA) make use-counting easy?
A7: Under SSA form, every value (%register) is defined exactly once in the text.
    Because there are no multiple assignments to the same register name,
    calculating how many times a value is used simply requires counting operand
    references across instructions in the function.

Q8: What are the main limitations of our model compared to production LLVM?
A8: Our implementation parses IR text with Python regex rather than LLVM's
    compiled C++ AST/CFG classes; it operates at function level without alias
    analysis; and it conservatively preserves potential faulting instructions.
================================================================================

