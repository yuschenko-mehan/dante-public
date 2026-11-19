"""External coding agents (e.g. OpenAI Codex CLI) as members of the DANTE team.

The agent edits files itself. DANTE stays in control:
- before the task the project is a git commit point (everything can be restored);
- after each agent attempt DANTE runs the check command itself (the agent's word is not trusted);
- protected paths (tests etc.) changed by the agent are restored and the attempt is rejected;
- if all attempts fail, the project is reset to the commit point.

Money: Codex is used ONLY through the author's own ChatGPT sign-in (plan allowance).
DANTE never passes an API key to it (that would be pay-per-token).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from dante import gitutil
from dante.audit import AuditLog
from dante.config import Settings
from dante.loop import LoopResult
from dante.runner import run_command


@dataclass
class AgentRun:
    exit_code: int
    output: str
    seconds: float


class CodexAgent:
    name = "codex"

    def __init__(self, command: list[str] | None = None, timeout_s: int = 900):
        self.command = command or _find_codex()
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return shutil.which(self.command[0]) is not None or Path(self.command[0]).exists()

    def run(self, prompt: str, root: Path) -> AgentRun:
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY")}  # money rule
        cmd = [*self.command, "exec", "--full-auto", "--skip-git-repo-check", "--cd", str(root), prompt]
        start = time.monotonic()
        try:
            p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=self.timeout_s)
            out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
        except subprocess.TimeoutExpired:
            out, code = f"TIMEOUT after {self.timeout_s}s", 124
        except OSError as e:
            out, code = f"cannot start agent: {e}", 127
        return AgentRun(code, out[-8000:], round(time.monotonic() - start, 2))


def _npm_entry(package: str, binname: str) -> list[str] | None:
    """On Windows npm installs a .cmd shim; long prompts with quotes/newlines break through cmd.exe,
    so run the package's JavaScript entry point with node directly (path read from package.json)."""
    import json
    node = shutil.which("node")
    found = shutil.which(binname)
    roots = []
    if found:
        roots.append(Path(found).parent / "node_modules")
    if os.name == "nt":
        roots.append(Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules")
    for r in roots:
        pkg = r / package / "package.json"
        if node and pkg.exists():
            try:
                b = json.loads(pkg.read_text(encoding="utf-8")).get("bin")
                rel = b if isinstance(b, str) else (b or {}).get(binname)
                if rel and (pkg.parent / rel).exists():
                    return [node, str(pkg.parent / rel)]
            except (OSError, ValueError):
                pass
    return None


def _find_cli(package: str, binname: str) -> list[str]:
    found = shutil.which(binname)
    if found and not found.lower().endswith((".cmd", ".bat")):
        return [found]
    return _npm_entry(package, binname) or [found or binname]


def _find_codex() -> list[str]:
    return _find_cli("@openai/codex", "codex")


class GeminiAgent:
    """Google Gemini CLI as an agent. Free path: the author's free AI Studio key (GEMINI_API_KEY from keys.txt).
    Money rule: Vertex / Google Cloud variables are removed, so only the free AI Studio key is used.
    (The key stays free while billing is NOT enabled on its Google project.)"""
    name = "gemini"

    def __init__(self, command: list[str] | None = None, timeout_s: int = 900, model: str | None = None):
        self.command = command or _find_cli("@google/gemini-cli", "gemini")
        self.timeout_s = timeout_s
        if model is None:  # the same model DANTE already uses on the free key (the CLI default is often overloaded: 503)
            from dante.config import DEFAULT_PROVIDERS
            model = next((p.model for p in DEFAULT_PROVIDERS if p.name == "gemini"), None)
        self.model = model

    def available(self) -> bool:
        return shutil.which(self.command[0]) is not None or Path(self.command[0]).exists()

    def run(self, prompt: str, root: Path) -> AgentRun:
        from dante.config import _file_keys
        drop = ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS",
                "GOOGLE_API_KEY", "OPENAI_API_KEY")
        env = {k: v for k, v in os.environ.items() if k not in drop}
        key = env.get("GEMINI_API_KEY") or _file_keys().get("GEMINI_API_KEY", "")
        if key:
            env["GEMINI_API_KEY"] = key
        # headless run: trust only this project folder (it is a git checkpoint, DANTE restores it on failure)
        env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
        cmd = [*self.command, "--yolo"]
        if self.model:
            cmd += ["-m", self.model]
        cmd += ["-p", prompt]
        start = time.monotonic()
        try:
            p = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=self.timeout_s)
            out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
        except subprocess.TimeoutExpired:
            out, code = f"TIMEOUT after {self.timeout_s}s", 124
        except OSError as e:
            out, code = f"cannot start agent: {e}", 127
        return AgentRun(code, out[-8000:], round(time.monotonic() - start, 2))


AGENTS = {"codex": CodexAgent, "gemini": GeminiAgent}


def make_agent(name: str):
    return AGENTS[name]()


def _changed_paths(root: Path) -> list[str]:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    paths = [line[3:].strip().strip('"') for line in r.stdout.splitlines() if line.strip()]
    # Python cache made when the agent runs the tests itself is noise, not a change to protected files
    return [x for x in paths if "__pycache__" not in x and not x.endswith(".pyc")]


def _is_protected(path: str, protected: tuple[str, ...]) -> bool:
    p = path.replace("\\", "/")
    return any(p == x or p.startswith(x.rstrip("/") + "/") for x in protected)


def _reset(root: Path) -> None:
    subprocess.run(["git", "reset", "--hard", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "clean", "-fdq"], cwd=root, capture_output=True)


def run_agent_task(task: str, test_command: str, root: Path, agent, settings: Settings, audit: AuditLog,
                   protect: tuple[str, ...] = ()) -> LoopResult:
    if not gitutil.ensure_repo(root):
        return LoopResult(False, 0, error="Git is required for agent mode (to restore the project)")
    gitutil.commit(root, "checkpoint before agent task")
    protect = tuple(protect) + (".dante", ".git")
    audit.log("agent_task_start", agent=agent.name, task=task, test_command=test_command)
    feedback = ""
    last_error = None
    last_run = None
    for attempt in range(1, settings.max_fix_attempts + 1):
        prompt = (f"{task}\n\nThe change must make this check pass: {test_command}\n"
                  f"Do NOT modify these paths: {', '.join(protect)}.")
        if feedback:
            prompt += f"\n\nPrevious attempt failed. Check output:\n{feedback[-3000:]}\nFix it."
        run = agent.run(prompt, root)
        changed = _changed_paths(root)
        audit.log("agent_attempt", attempt=attempt, exit_code=run.exit_code, seconds=run.seconds,
                  changed=changed, output_tail=run.output[-1500:])
        bad = [c for c in changed if _is_protected(c, protect)]
        if bad:
            subprocess.run(["git", "checkout", "--", *bad], cwd=root, capture_output=True)
            feedback = f"You changed protected files {bad}; they were restored. Do not touch them."
            continue
        if run.exit_code != 0 and not changed:
            feedback = f"Agent error (exit {run.exit_code}):\n{run.output[-1500:]}"
            if run.exit_code in (124, 127) or run.output == last_error:
                break  # timeout / not installed / same setup error again: retrying will not help
            last_error = run.output
            continue
        last_run = run_command(test_command, root, settings.command_timeout_s)
        audit.log("test_run", attempt=attempt, exit_code=last_run.exit_code, output_tail=last_run.output[-2000:])
        if last_run.ok:
            audit.log("task_success", attempts=attempt, files=changed)
            return LoopResult(True, attempt, changed, last_run, models=[agent.name] * attempt)
        feedback = last_run.output
    _reset(root)
    audit.log("task_failed", attempts=settings.max_fix_attempts)
    return LoopResult(False, settings.max_fix_attempts, [], last_run, "All agent attempts failed", [agent.name])
