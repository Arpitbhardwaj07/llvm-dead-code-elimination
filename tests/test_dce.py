"""
Unit tests for the LLVM Dead Code Elimination (DCE) algorithm.
Tests operate directly on hand-crafted LLVM IR text strings (no Clang required).
"""

import unittest
import sys
import os

# Add project root directory to sys.path so dce can be imported directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dce import run_dce


class TestDCE(unittest.TestCase):

    def test_zero_use_add_removed(self):
        """Test that a pure arithmetic instruction with zero uses is removed."""
        ir = (
            "define i32 @test(i32 %a, i32 %b) {\n"
            "entry:\n"
            "  %dead = add i32 %a, %b\n"
            "  ret i32 %a\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertNotIn("%dead = add", res["after_ir"])
        self.assertIn("ret i32 %a", res["after_ir"])
        self.assertEqual(len(res["removed"]), 1)
        self.assertEqual(res["removed"][0]["function"], "@test")
        self.assertEqual(res["removed"][0]["block"], "entry")
        self.assertEqual(res["removed"][0]["reason"], "result %dead is never used")

    def test_cascade_removal_three_steps(self):
        """Test a 3-step cascade: %c depends on %b which depends on %a."""
        ir = (
            "define i32 @cascade(i32 %n) {\n"
            "entry:\n"
            "  %a = mul i32 %n, 2\n"
            "  %b = add i32 %a, 10\n"
            "  %c = sub i32 %b, 1\n"
            "  ret i32 %n\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertNotIn("%a = mul", res["after_ir"])
        self.assertNotIn("%b = add", res["after_ir"])
        self.assertNotIn("%c = sub", res["after_ir"])
        self.assertIn("ret i32 %n", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 3)
        self.assertEqual(res["stats"]["after"], 1)  # Only ret remains
        # Must take multiple rounds to resolve cascade
        self.assertGreaterEqual(len(res["rounds"]), 3)
        # Final round must report 0 removed
        self.assertEqual(res["rounds"][-1]["removed"], 0)

    def test_call_kept_even_if_result_unused(self):
        """Test that function calls are preserved because they may have side effects."""
        ir = (
            "declare i32 @side_effect(i32)\n"
            "define i32 @caller(i32 %x) {\n"
            "entry:\n"
            "  %unused_call = call i32 @side_effect(i32 %x)\n"
            "  ret i32 %x\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertIn("call i32 @side_effect", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 0)

    def test_volatile_load_kept(self):
        """Test that volatile loads are preserved to respect hardware/volatile semantics."""
        ir = (
            "define i32 @volatile_test(ptr %p) {\n"
            "entry:\n"
            "  %val = load volatile i32, ptr %p, align 4\n"
            "  ret i32 0\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertIn("load volatile", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 0)

    def test_store_to_global_kept(self):
        """Test that stores to global variables are strictly preserved."""
        ir = (
            "@count = global i32 0, align 4\n"
            "define void @inc() {\n"
            "entry:\n"
            "  store i32 42, ptr @count, align 4\n"
            "  ret void\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertIn("store i32 42, ptr @count", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 0)

    def test_write_only_alloca_and_stores_removed(self):
        """Test Rule C: a stack variable allocated and stored to, but never read, is erased."""
        ir = (
            "define i32 @write_only(i32 %x) {\n"
            "entry:\n"
            "  %v = alloca i32, align 4\n"
            "  store i32 %x, ptr %v, align 4\n"
            "  store i32 100, ptr %v, align 4\n"
            "  ret i32 %x\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertNotIn("%v = alloca", res["after_ir"])
        self.assertNotIn("store i32 %x, ptr %v", res["after_ir"])
        self.assertNotIn("store i32 100, ptr %v", res["after_ir"])
        self.assertIn("ret i32 %x", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 3)
        for rem in res["removed"]:
            self.assertEqual(rem["reason"], "variable %v is written but never read")

    def test_read_alloca_kept(self):
        """Test that an alloca loaded/read anywhere in the function is kept intact."""
        ir = (
            "define i32 @read_alloca(i32 %x) {\n"
            "entry:\n"
            "  %v = alloca i32, align 4\n"
            "  store i32 %x, ptr %v, align 4\n"
            "  %loaded = load i32, ptr %v, align 4\n"
            "  ret i32 %loaded\n"
            "}\n"
        )
        res = run_dce(ir)
        self.assertIn("%v = alloca", res["after_ir"])
        self.assertIn("store i32 %x, ptr %v", res["after_ir"])
        self.assertIn("%loaded = load", res["after_ir"])
        self.assertEqual(res["stats"]["removed"], 0)

    def test_lines_outside_functions_unchanged(self):
        """Test that datalayout, target triple, attributes, metadata outside functions remain identical."""
        ir = (
            '; ModuleID = "sample.c"\n'
            'source_filename = "sample.c"\n'
            'target datalayout = "e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"\n'
            'target triple = "x86_64-pc-windows-msvc"\n'
            "@g = global i32 10\n"
            "define i32 @f() {\n"
            "entry:\n"
            "  %d = add i32 1, 2\n"
            "  ret i32 0\n"
            "}\n"
            "!0 = !{i32 1, !\"wchar_size\", i32 2}\n"
        )
        res = run_dce(ir)
        self.assertIn('target triple = "x86_64-pc-windows-msvc"', res["after_ir"])
        self.assertIn('@g = global i32 10', res["after_ir"])
        self.assertIn('!0 = !{i32 1, !"wchar_size", i32 2}', res["after_ir"])
        self.assertNotIn("%d = add", res["after_ir"])

    def test_stats_and_rounds_structure(self):
        """Test that stats counts and rounds structure match exact specifications."""
        ir = (
            "define i32 @math(i32 %a) {\n"
            "entry:\n"
            "  %x = add i32 %a, 1\n"
            "  %y = sub i32 %a, 2\n"
            "  ret i32 %a\n"
            "}\n"
        )
        res = run_dce(ir)
        stats = res["stats"]
        self.assertEqual(stats["before"], 3)  # add, sub, ret
        self.assertEqual(stats["removed"], 2)  # add, sub
        self.assertEqual(stats["after"], 1)    # ret
        self.assertEqual(stats["percent"], 66.7)
        self.assertEqual(len(stats["per_function"]), 1)
        self.assertEqual(stats["per_function"][0]["name"], "@math")
        self.assertEqual(stats["per_function"][0]["before"], 3)
        self.assertEqual(stats["per_function"][0]["after"], 1)
        
        # Rounds check
        self.assertGreaterEqual(len(res["rounds"]), 2)
        self.assertEqual(res["rounds"][-1]["removed"], 0)

    def test_removed_entries_carry_right_block_name(self):
        """Test that instructions removed from different basic blocks record accurate block names."""
        ir = (
            "define i32 @branches(i32 %a) {\n"
            "entry:\n"
            "  %dead_entry = add i32 %a, 1\n"
            "  br label %second_block\n"
            "second_block:\n"
            "  %dead_second = mul i32 %a, 5\n"
            "  ret i32 %a\n"
            "}\n"
        )
        res = run_dce(ir)
        blocks = {item["block"] for item in res["removed"]}
        self.assertIn("entry", blocks)
        self.assertIn("second_block", blocks)


if __name__ == "__main__":
    unittest.main()

