"""
Integration tests for Clang compilation and DCE pipeline.
Tests run all sample C examples through the full flow:
C code -> Clang unoptimized LLVM IR -> DCE pass -> Verified optimization.
Skips cleanly if Clang is not installed on the system.
"""

import unittest
import sys
import os

# Add project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from compiler import find_clang, compile_to_ir, get_all_compiler_phases
from dce import run_dce
from examples import get_examples


class TestCompilerIntegration(unittest.TestCase):

    def setUp(self):
        self.clang_bin = find_clang()
        if not self.clang_bin:
            self.skipTest("Clang not found on PATH or CLANG_PATH. Skipping integration tests.")

    def test_all_examples_compilation_and_dce(self):
        """Verify that every sample example compiles with Clang and processes through DCE."""
        examples = get_examples()
        for eg in examples:
            with self.subTest(example_name=eg["name"]):
                # Step 1: Compile C to IR
                ir_res = compile_to_ir(eg["code"])
                self.assertTrue(ir_res["ok"], f"Clang failed on {eg['name']}: {ir_res.get('details')}")
                before_ir = ir_res["ir"]
                self.assertIn("define ", before_ir)

                # Step 2: Run DCE
                dce_res = run_dce(before_ir)
                self.assertIn("after_ir", dce_res)
                self.assertIn("stats", dce_res)
                self.assertIn("rounds", dce_res)

                # Step 3: Specific checks for certain examples
                if "Side Effect" in eg["name"]:
                    self.assertIn("putchar", dce_res["after_ir"], "putchar call must not be removed")
                elif "Global Store" in eg["name"]:
                    self.assertIn("@counter", dce_res["after_ir"], "global store must not be removed")
                elif "Clean Code" in eg["name"]:
                    self.assertEqual(dce_res["stats"]["removed"], 0, "No code should be removed from clean example")
                elif "Cascade" in eg["name"]:
                    self.assertGreater(dce_res["stats"]["removed"], 0, "Cascade example must remove dead lines")

    def test_compiler_phases_pipeline(self):
        """Test the extraction of all 5 compiler phases on a simple program."""
        code = "int square(int x) { int dead = x + 10; return x * x; }"
        res = get_all_compiler_phases(code)
        self.assertTrue(res["ok"])
        phases = res["phases"]
        self.assertTrue(phases["tokens"]["ok"], "Tokens phase should succeed")
        self.assertTrue(phases["ast"]["ok"], "AST phase should succeed")
        self.assertTrue(phases["ir_before"]["ok"], "IR before phase should succeed")
        self.assertTrue(phases["ir_after"]["ok"], "IR after phase should succeed")
        self.assertTrue(phases["assembly"]["ok"], "Assembly phase should succeed")


if __name__ == "__main__":
    unittest.main()

