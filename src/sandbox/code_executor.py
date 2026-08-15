"""
EduScribe AI - Code Executor Sandbox Module
Safely validates Python starter code and test execution in an isolated subprocess.
"""

import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class CodeExecutor:
    @staticmethod
    def execute_python_code(code_string: str, working_dir: Path, timeout_sec: int = 5) -> Dict[str, Any]:
        """Runs Python starter code and returns stdout, stderr, and exit status."""
        working_dir.mkdir(parents=True, exist_ok=True)
        script_path = working_dir / "temp_run.py"
        
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code_string)

        try:
            res = subprocess.run(
                [sys.executable, script_path.name],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout_sec} seconds.",
                "exit_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1
            }
