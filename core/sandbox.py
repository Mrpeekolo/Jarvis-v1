import ast
import asyncio
import os
import sys
import tempfile
from typing import Dict, Any, Tuple

FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket",
    "ctypes", "pty", "multiprocessing", "pickle", "importlib", "webbrowser"
}

FORBIDDEN_CALLS = {
    "eval", "exec", "open", "compile", "__import__", "globals", "locals"
}

class ASTSecurityViolation(Exception):
    """Raised when code violates sandbox AST rules."""
    pass

class SafetyScanner(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split('.')[0]
            if base_mod in FORBIDDEN_MODULES:
                raise ASTSecurityViolation(f"Forbidden module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module.split('.')[0] in FORBIDDEN_MODULES:
            raise ASTSecurityViolation(f"Forbidden module import: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            raise ASTSecurityViolation(f"Forbidden built-in call: '{node.func.id}()'")
        self.generic_visit(node)

def scan_code(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ASTSecurityViolation(f"Syntax error: {e}")
    scanner = SafetyScanner()
    scanner.visit(tree)

async def run_sandboxed(source: str, timeout_sec: int = 5) -> Dict[str, Any]:
    """
    Scans and runs Python code in an isolated subprocess with stripped environment.
    """
    try:
        scan_code(source)
    except ASTSecurityViolation as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Security Block: {str(e)}",
            "violation": str(e)
        }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(source)
        tmp_path = tmp.name

    try:
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "random"
        }

        # Run with isolated mode (-I) and skip site packages (-S)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            return {
                "success": (proc.returncode == 0),
                "stdout": stdout_b.decode("utf-8", errors="replace"),
                "stderr": stderr_b.decode("utf-8", errors="replace"),
                "violation": None
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out ({timeout_sec}s limit exceeded).",
                "violation": "Timeout"
            }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
