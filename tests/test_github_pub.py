"""Specification for dante/github_pub.py — safe, bilingual publishing of a project to GitHub.

Pure logic only (no network, no git calls). Python standard library only.

EXCLUDE_DIRS  = {".git", "__pycache__", "audit", "node_modules", ".venv", "venv", "chrome-dante", ".pytest_cache"}
EXCLUDE_FILES = {"keys.txt", ".env", "dante.toml", "models.json"}   plus any name ending in
                .pem .key .pfx .p12  and any name starting with "id_rsa" or "id_ed25519"

files_to_publish(root, max_bytes=50*1024*1024) -> sorted list of POSIX relative paths of regular files
    under root, skipping excluded dirs (at any depth), excluded files, symlinks and files bigger than max_bytes.

SECRET_PATTERNS: dict name -> compiled regex, at least these names:
    "github" ghp_ + 36 [A-Za-z0-9];  "github_pat" github_pat_ + 50+ [A-Za-z0-9_];
    "openai" sk- + 20+ [A-Za-z0-9_-];  "groq" gsk_ + 20+ [A-Za-z0-9];  "google" AIza + 35 [0-9A-Za-z_-];
    "huggingface" hf_ + 30+ [A-Za-z0-9];  "nvidia" nvapi- + 20+ [A-Za-z0-9_-];
    "private_key" -----BEGIN ... PRIVATE KEY-----;
    "key_assignment" a line like  NAME_API_KEY=value / NAME_TOKEN = value / NAME_SECRET=value
        (NAME is [A-Z][A-Z0-9_]*, may be empty prefix: API_KEY=..., value of 8+ non-space chars, not starting with $ or %)
find_secrets(text) -> list of (pattern_name, line_number_from_1), ordered by line, then name; each name once per line.
    The secret value itself is never returned.
scan_project(root) -> list of (relpath, pattern_name, line) over files_to_publish(root); files whose first
    8192 bytes contain a NUL byte are skipped (binary); text read as UTF-8 with errors="replace".

repo_name(folder) -> GitHub-safe name: Ukrainian letters transliterated (KMU 2010, the non-initial forms everywhere:
    а a б b в v г h ґ g д d е e є ie ж zh з z и y і i ї i й i к k л l м m н n о o п p р r с s т t у u ф f х kh
    ц ts ч ch ш sh щ shch ь (nothing) ю iu я ia, apostrophes ' ’ ʼ removed), lower case, every run of characters
    other than [a-z0-9._] becomes one "-", leading/trailing "-" and "." removed, at most 100 chars
    (cut, then strip again), empty result -> "dante-project".

GITIGNORE: text with one entry per line, containing at least: keys.txt .env dante.toml models.json audit/
    __pycache__/ *.pyc chrome-dante/

commit_message(summary_uk, summary_en, files) -> str:
    line 1: "<summary_en> / <summary_uk>" if that is <= 72 chars, else summary_en cut to 72 chars
    line 2: empty
    line 3: "UK: <summary_uk>"
    line 4: "EN: <summary_en>"
    line 5: empty
    line 6: "Files / Файли:"
    then "- <file>" for the first 20 files, then "- … +N" if more
    last line: "Published by DANTE"
    summaries are stripped; newlines inside a summary become spaces; empty summary -> ValueError

publish_commands(repo, visibility, has_git, has_remote, message, description="") -> list of argv lists:
    visibility must be "private" or "public" (else ValueError); repo must equal repo_name(repo) (else ValueError)
    not has_git -> first ["git", "init", "-b", "main"]
    then ["git", "add", "-A"], then ["git", "commit", "-m", message]
    not has_remote -> ["gh", "repo", "create", repo, "--private"|"--public", "--source", ".", "--remote", "origin",
                       "--push"] + (["--description", description] if description else [])
    has_remote     -> ["git", "push", "-u", "origin", "HEAD"]

readme_files(readme_uk, readme_en) -> {"README.md": en, "README.uk.md": uk}
    README.md starts with the line "🇺🇦 [Українською](README.uk.md)" then an empty line, then the English text;
    README.uk.md starts with "🇬🇧 [English](README.md)" then an empty line, then the Ukrainian text.
    If the text already starts with its link line it is not added twice. Texts end with exactly one "\\n".
"""
import tempfile, unittest
from pathlib import Path

from dante import github_pub as G


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.r = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, rel, text="x", data=None):
        p = self.r / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data) if data is not None else p.write_text(text, encoding="utf-8")

    def test_excludes(self):
        for rel in ["app.py", "src/m.py", "keys.txt", ".env", "dante.toml", "models.json", "a/keys.txt",
                    ".git/config", "src/__pycache__/m.pyc", "audit/l.jsonl", "x/node_modules/a.js",
                    "server.pem", "my.key", "c.pfx", "c.p12", "id_rsa", "id_rsa.pub", "id_ed25519", "README.md",
                    "chrome-dante/Default/x", "venv/lib.py"]:
            self.w(rel)
        self.assertEqual(G.files_to_publish(self.r), ["README.md", "app.py", "src/m.py"])

    def test_big_files_skipped(self):
        self.w("big.bin", data=b"0" * 2000)
        self.w("small.txt", "ok")
        self.assertEqual(G.files_to_publish(self.r, max_bytes=1000), ["small.txt"])

    def test_scan_project(self):
        self.w("a.py", "x = 1\ntoken = 'ghp_" + "A" * 36 + "'\n")
        self.w("b.bin", data=b"\0ghp_" + b"A" * 36)
        self.w("keys.txt", "GROQ_API_KEY=gsk_" + "a" * 30)
        self.assertEqual(G.scan_project(self.r), [("a.py", "github", 2)])


class SecretsTest(unittest.TestCase):
    def test_each_pattern(self):
        cases = {
            "github": "ghp_" + "a1" * 18, "github_pat": "github_pat_" + "A_1" * 20, "openai": "sk-proj-" + "x" * 30,
            "groq": "gsk_" + "Ab1" * 10, "google": "AIza" + "S" * 35, "huggingface": "hf_" + "q" * 34,
            "nvidia": "nvapi-" + "Z9" * 15, "private_key": "-----BEGIN RSA PRIV" + "ATE KEY-----",  # built at runtime / збирається під час запуску
        }
        for name, s in cases.items():
            self.assertIn((name, 1), G.find_secrets(f"value: {s}"), name)

    def test_assignment(self):
        self.assertEqual(G.find_secrets("MISTRAL_API_KEY=abcdefgh123"), [("key_assignment", 1)])
        self.assertEqual(G.find_secrets("x\n  HF_TOKEN = abcdefghij"), [("key_assignment", 2)])
        self.assertEqual(G.find_secrets("API_KEY=12345678"), [("key_assignment", 1)])
        self.assertEqual(G.find_secrets("MY_SECRET=$ENV_VAR_FROM_SHELL"), [])
        self.assertEqual(G.find_secrets("MY_SECRET=%SECRET%"), [])
        self.assertEqual(G.find_secrets("API_KEY=short"), [])
        self.assertEqual(G.find_secrets("api_key = 'x'"), [])

    def test_clean_text_and_no_values(self):
        self.assertEqual(G.find_secrets("def f():\n    return 'sk-short'\n# skip-this\n"), [])
        res = G.find_secrets("a\nGROQ_API_KEY=gsk_" + "b" * 30)
        self.assertEqual(res, [("groq", 2), ("key_assignment", 2)])
        self.assertNotIn("bbbb", repr(res))

    def test_once_per_line(self):
        self.assertEqual(G.find_secrets("ghp_" + "a" * 36 + " ghp_" + "b" * 36), [("github", 1)])


class NamesTest(unittest.TestCase):
    def test_transliteration(self):
        self.assertEqual(G.repo_name("Мій калькулятор"), "mii-kalkuliator")
        self.assertEqual(G.repo_name("Щука"), "shchuka")
        self.assertEqual(G.repo_name("Зір Данте 2"), "zir-dante-2")
        self.assertEqual(G.repo_name("Ґанок, м'ята і їжак"), "ganok-miata-i-izhak")
        self.assertEqual(G.repo_name("Юля Єва Хата Цех Чай Шафа"), "iulia-ieva-khata-tsekh-chai-shafa")

    def test_ascii_rules(self):
        self.assertEqual(G.repo_name("My_Project.v2"), "my_project.v2")
        self.assertEqual(G.repo_name("  --hello   world!!  "), "hello-world")
        self.assertEqual(G.repo_name("..."), "dante-project")
        self.assertEqual(G.repo_name("!!!"), "dante-project")
        self.assertEqual(len(G.repo_name("a" * 101)), 100)
        self.assertEqual(G.repo_name("a" * 99 + "-b"), "a" * 99)


class TextsTest(unittest.TestCase):
    def test_gitignore(self):
        lines = G.GITIGNORE.splitlines()
        for x in ["keys.txt", ".env", "dante.toml", "models.json", "audit/", "__pycache__/", "*.pyc", "chrome-dante/"]:
            self.assertIn(x, lines)

    def test_commit_message(self):
        m = G.commit_message(" Додано калькулятор ", "Added calculator", ["calc.py", "tests/test_calc.py"])
        self.assertEqual(m.splitlines(), [
            "Added calculator / Додано калькулятор", "", "UK: Додано калькулятор", "EN: Added calculator", "",
            "Files / Файли:", "- calc.py", "- tests/test_calc.py", "Published by DANTE"])

    def test_commit_message_long_and_many_files(self):
        en = "E" * 80
        m = G.commit_message("у\nк", en, [f"f{i}.py" for i in range(25)]).splitlines()
        self.assertEqual(m[0], "E" * 72)
        self.assertEqual(m[2], "UK: у к")
        self.assertEqual(m[6:8], ["- f0.py", "- f1.py"])
        self.assertEqual(m[-2], "- … +5")
        self.assertEqual(len([x for x in m if x.startswith("- f")]), 20)
        with self.assertRaises(ValueError):
            G.commit_message("  ", "x", [])

    def test_publish_commands_new_repo(self):
        cmds = G.publish_commands("calc", "private", has_git=False, has_remote=False, message="m", description="d")
        self.assertEqual(cmds, [["git", "init", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-m", "m"],
                                ["gh", "repo", "create", "calc", "--private", "--source", ".", "--remote", "origin",
                                 "--push", "--description", "d"]])

    def test_publish_commands_existing(self):
        cmds = G.publish_commands("calc", "public", has_git=True, has_remote=True, message="m")
        self.assertEqual(cmds, [["git", "add", "-A"], ["git", "commit", "-m", "m"], ["git", "push", "-u", "origin", "HEAD"]])
        self.assertEqual(G.publish_commands("calc", "public", True, False, "m")[-1][-1], "--push")

    def test_publish_commands_checks(self):
        with self.assertRaises(ValueError):
            G.publish_commands("calc", "internal", True, True, "m")
        with self.assertRaises(ValueError):
            G.publish_commands("Bad Name", "private", True, True, "m")

    def test_readme_files(self):
        r = G.readme_files("# Калькулятор\nОпис\n\n\n", "# Calculator\nAbout")
        self.assertEqual(r["README.md"], "🇺🇦 [Українською](README.uk.md)\n\n# Calculator\nAbout\n")
        self.assertEqual(r["README.uk.md"], "🇬🇧 [English](README.md)\n\n# Калькулятор\nОпис\n")
        again = G.readme_files(r["README.uk.md"], r["README.md"])
        self.assertEqual(again, r)


class ReviewFindingsTest(unittest.TestCase):
    """Defects found by Claude in DANTE's first version (19.11.2026).
    Вади, які Claude знайшов у першій версії Данте (19.11.2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.r = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_assignment_is_a_named_pattern(self):
        self.assertIn("key_assignment", G.SECRET_PATTERNS)

    def test_bare_token_and_secret(self):
        self.assertEqual(G.find_secrets("TOKEN=abcdefgh1"), [("key_assignment", 1)])
        self.assertEqual(G.find_secrets("SECRET = abcdefgh1"), [("key_assignment", 1)])

    def test_utf8_cut_at_8192_bytes_reads_whole_text_once(self):
        text = "я" * 4097 + "\nGROQ=gsk_" + "a" * 30 + "\n"  # 8194 bytes before the newline
        (self.r / "u.txt").write_text(text, encoding="utf-8")
        self.assertEqual(G.scan_project(self.r), [("u.txt", "groq", 2)])


if __name__ == "__main__":
    unittest.main()
