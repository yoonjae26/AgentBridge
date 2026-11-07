import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests" / "test_calculator.py"
ORIGINAL_SHA256 = "714e4f0678ea032c81690412a4b595f3ee45a16f9e77ae26a5b829ac3c367334"
MUTANTS = {
    "add": ("return a + b", "return a - b"),
    "multiply": ("return a * b", "return a + b"),
    "divide_zero": ('raise ValueError("division by zero")', "return 0"),
    "subtract": ("return a - b", "return b - a"),
}


def run_tests(directory):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_calculator.py"],
        cwd=directory, capture_output=True, text=True, timeout=120,
    )


def test_file_has_enough_tests():
    assert TESTS.exists()
    assert TESTS.read_text(encoding="utf-8").count("def test_") >= 5


def test_calculator_unchanged():
    content = (ROOT / "calculator.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(content).hexdigest() == ORIGINAL_SHA256


def test_tests_pass_on_original():
    assert run_tests(ROOT).returncode == 0


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_tests_detect_mutant(name, tmp_path):
    old, new = MUTANTS[name]
    shutil.copytree(ROOT / "tests", tmp_path / "tests")
    source = (ROOT / "calculator.py").read_text(encoding="utf-8")
    (tmp_path / "calculator.py").write_text(source.replace(old, new), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    assert run_tests(tmp_path).returncode != 0, f"mutant {name} survived"
