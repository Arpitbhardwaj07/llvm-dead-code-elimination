"""
Sample C programs for testing and demonstrating LLVM Dead Code Elimination.
All programs use function arguments or external symbols so Clang cannot fold
constants upfront at -O0. Standard C library functions use extern declarations
rather than #include to keep intermediate IR minimal and readable.
"""

from typing import List, Dict

EXAMPLES: List[Dict[str, str]] = [
    {
        "name": "1. Unused Variable (Basic Cascade)",
        "description": "Computations for 'a' and 'b' are never returned or read. Both are eliminated across multiple rounds.",
        "code": (
            "int f(int n) {\n"
            "    int a = n * 2;\n"
            "    int b = a + 5;\n"
            "    return n;\n"
            "}\n"
            "\n"
            "int main(void) {\n"
            "    return f(3);\n"
            "}\n"
        )
    },
    {
        "name": "2. Dead Calculation Chain with Used Result",
        "description": "Independent dead expressions are pruned while the expression contributing to the return value is preserved.",
        "code": (
            "int compute(int x, int y) {\n"
            "    int dead1 = x + 10;\n"
            "    int dead2 = dead1 * y;\n"
            "    int dead3 = dead2 ^ 3;\n"
            "    int used = x * 2 + y;\n"
            "    return used;\n"
            "}\n"
        )
    },
    {
        "name": "3. Side Effect Preservation (Call Kept)",
        "description": "Unused math is safely deleted, but the external function call (putchar) is strictly kept because calls may have side effects.",
        "code": (
            "extern int putchar(int c);\n"
            "\n"
            "int g(int n) {\n"
            "    int unused = n * 3;\n"
            "    putchar(65); // Side effect: prints 'A'\n"
            "    return n + 1;\n"
            "}\n"
        )
    },
    {
        "name": "4. Clean Code (Zero Dead Code)",
        "description": "Every instruction contributes to the returned sum. Our optimizer leaves the IR 100% intact.",
        "code": (
            "int add(int a, int b) {\n"
            "    return a + b;\n"
            "}\n"
        )
    },
    {
        "name": "5. Global Store Preservation",
        "description": "Local unused calculation 't' is removed, but the store updating the global variable 'counter' is strictly retained.",
        "code": (
            "int counter = 0;\n"
            "\n"
            "void inc(void) {\n"
            "    int t = counter * 2;\n"
            "    counter = counter + 1;\n"
            "}\n"
        )
    },
    {
        "name": "6. Loop with Dead Value",
        "description": "An unused computation inside a for-loop body is removed while the loop control flow and accumulator remain intact.",
        "code": (
            "int loop_test(int n) {\n"
            "    int total = 0;\n"
            "    for (int i = 0; i < n; i++) {\n"
            "        int dead_metric = (i * 7) ^ 3;\n"
            "        total += i;\n"
            "    }\n"
            "    return total;\n"
            "}\n"
        )
    },
    {
        "name": "7. Deep Cascade Chain (5 Dependent Rounds)",
        "description": "A 5-level dependency chain (e -> d -> c -> b -> a). Each round exposes the next dead instruction until fixed-point.",
        "code": (
            "int deep_cascade(int x) {\n"
            "    int a = x + 1;\n"
            "    int b = a * 2;\n"
            "    int c = b - 3;\n"
            "    int d = c ^ 4;\n"
            "    int e = d + 5;\n"
            "    return x;\n"
            "}\n"
        )
    }
]


def get_examples() -> List[Dict[str, str]]:
    """Return list of sample programs for frontend dropdown and test cases."""
    return EXAMPLES

