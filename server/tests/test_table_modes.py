"""Table switches, engine commands, worker cleanup, and version fallback."""

import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import toml
from utils import table_process, table_runner, table_runtime
from utils.config import Config


class TableModeTests(unittest.TestCase):
    def test_task_config_does_not_inherit_another_tasks_table_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = {"provider": "openaicompatible", "apiKey": "", "apiUrl": "", "model": "", "extraData": {}}
            for enabled, mode, expected in [(False, "", False), (True, "", True), (True, "fixed", False), (True, "preserve", False)]:
                with self.subTest(enabled=enabled, mode=mode):
                    path = Path(temp) / "config.toml"
                    Config({"translateTableText": enabled, "tableMode": mode}).write(profile, path, Path(temp))
                    self.assertIs(toml.load(path)["pdf"]["translate_table_text"], expected)


class TableProcessTests(unittest.TestCase):
    def test_policy_runs_once_in_real_child_and_restores_parent(self):
        server = Path(__file__).resolve().parents[1]
        fixture = server / "tests" / "fixtures" / "table_process_probe.py"
        env = {**os.environ, "PYTHONPATH": str(server)}
        # Always test spawn, even on Linux CI. Fork must not double-install
        # inherited hooks where that start method is available.
        import itertools
        for method, scenario in itertools.product(multiprocessing.get_all_start_methods(), ("table", "model", "combined")):
            with self.subTest(method=method, scenario=scenario):
                result = subprocess.run(
                    [sys.executable, str(fixture), method, scenario],
                    check=False,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                state = json.loads(result.stdout)
                self.assertEqual(state["mode"], None if scenario == "model" else "fixed")
                self.assertEqual(state["installs"], int(scenario != "model"))
                self.assertEqual(state["modelInstalls"], int(scenario != "table"))


class TableVersionFallbackTests(unittest.TestCase):
    def test_runner_fallback_enables_native_tables_without_installing_hooks(self):
        for mode in ("fixed", "preserve"):
            for existing_flag in ([], ["--translate-table-text"]):
                with self.subTest(mode=mode, existing_flag=existing_flag):
                    arguments = [
                        "table_runner.py",
                        mode,
                        "paper.pdf",
                        "--config-file",
                        "settings.toml",
                        *existing_flag,
                    ]
                    observed = []

                    def native_cli():
                        observed.extend(sys.argv)
                        return 17

                    entry = SimpleNamespace(
                        group="console_scripts",
                        name="pdf2zh_next",
                        load=lambda: native_cli,
                    )
                    install = Mock(side_effect=AssertionError("unexpected hook"))
                    with (
                        patch.object(sys, "argv", arguments),
                        patch("importlib.metadata.version", return_value="0.7.0"),
                        patch(
                            "importlib.metadata.distribution",
                            return_value=SimpleNamespace(entry_points=[entry]),
                        ),
                        patch.object(
                            table_process, "install_table_process_policy", install
                        ),
                        self.assertLogs(table_runtime.logger, level="WARNING"),
                    ):
                        self.assertEqual(table_runner.main(), 17)
                    install.assert_not_called()
                    self.assertEqual(observed[0], "pdf2zh_next")
                    self.assertEqual(observed.count("--translate-table-text"), 1)
                    self.assertNotIn(mode, observed)
                    self.assertIn("settings.toml", observed)


if __name__ == "__main__":
    unittest.main()
