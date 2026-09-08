"""Tests for tk. Standard library only, same as the tool itself.

Run with: python3 -m unittest discover -s tests -v
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tk")


def import_tk():
    """Import tk as a module. It has no .py suffix, so spell it out."""
    spec = importlib.util.spec_from_loader(
        "tk", importlib.machinery.SourceFileLoader("tk", TK))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    """A temp store and a temp working directory, never the user's own."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tk-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "store")
        self.work = os.path.join(self.tmp, "work")
        self.legacy = os.path.join(self.tmp, "legacy")
        os.makedirs(self.work)
        here = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, here)

        self.tk = import_tk()
        self.tk.STORE = self.store
        self.tk.LEGACY_STORE = self.legacy
        self.tk.SESSION = ""

    def env(self, **extra):
        e = dict(os.environ)
        e.pop("NO_COLOR", None)
        e.update({
            "TICKMARK_STORE": self.store,
            "HOME": self.tmp,
            "LC_ALL": "C",
            "LANG": "C",
            "LC_MESSAGES": "C",
        })
        e.update(extra)
        return e

    def run_tk(self, *args, **kwargs):
        return subprocess.run(
            [sys.executable, TK] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, cwd=self.work,
            env=self.env(**kwargs.pop("env", {})), **kwargs)

    def run_pty(self, *args, **extra_env):
        """Run tk with a real terminal on stdout, so isatty() is true."""
        try:
            master, slave = os.openpty()
        except OSError as exc:  # restricted container, sandbox, no pty device
            raise unittest.SkipTest("no pty available here: %s" % exc)
        p = subprocess.Popen(
            [sys.executable, TK] + list(args), stdout=slave,
            stderr=subprocess.DEVNULL, cwd=self.work,
            env=self.env(TERM="xterm", **extra_env))
        os.close(slave)
        out = b""
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        p.wait()
        os.close(master)
        return out.decode("utf-8", "replace")


# --- defect 1: save() was not atomic -------------------------------------

class SaveIsAtomic(Base):

    def test_failed_write_leaves_the_previous_list_intact(self):
        self.tk.save([{"t": "kept", "s": "todo"}])
        with mock.patch.object(self.tk.json, "dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.tk.save([{"t": "lost", "s": "todo"}])
        self.assertEqual(self.tk.load(), [{"t": "kept", "s": "todo"}])

    def test_no_temp_file_is_left_behind(self):
        self.tk.save([{"t": "a", "s": "todo"}])
        leftovers = [f for f in os.listdir(self.store) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_concurrent_writers_never_expose_a_half_written_file(self):
        # A big list so json.dump flushes several times per save: that is the
        # window in which a non-atomic write is visible to a reader.
        big = [{"t": "task %d %s" % (i, "x" * 200), "s": "todo"}
               for i in range(400)]
        self.tk.save(big)
        path = self.tk.state_path()
        self.assertGreater(os.path.getsize(path), 64 * 1024)

        writers = [subprocess.Popen(
            [sys.executable, TK, "add", "concurrent %d" % i],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=self.work, env=self.env()) for i in range(6)]
        reads = 0
        while any(w.poll() is None for w in writers):
            try:
                with open(path) as f:
                    data = json.load(f)
            except FileNotFoundError:
                continue
            except json.JSONDecodeError as exc:
                self.fail("reader saw a half-written file: %s" % exc)
            self.assertIsInstance(data, list)
            self.assertNotEqual(data, [], "reader saw an emptied list")
            reads += 1
        for w in writers:
            self.assertEqual(w.wait(), 0)
        self.assertGreater(reads, 0, "the concurrency window was never sampled")
        self.assertEqual(
            [f for f in os.listdir(self.store) if f.endswith(".tmp")], [])


# --- defect 2: one list per project, split only when asked ----------------

class SessionIsolation(Base):

    def test_without_a_session_the_file_name_is_unchanged(self):
        root = self.tk.project_root()
        expected = hashlib.sha1(root.encode()).hexdigest()[:16] + ".json"
        self.assertEqual(os.path.basename(self.tk.state_path()), expected)

    def test_two_sessions_in_one_checkout_keep_separate_lists(self):
        first = self.run_tk("add", "worker one", env={"TICKMARK_SESSION": "a"})
        second = self.run_tk("add", "worker two", env={"TICKMARK_SESSION": "b"})
        self.assertIn("worker one", first.stdout)
        self.assertNotIn("worker one", second.stdout)
        back = self.run_tk("--json", env={"TICKMARK_SESSION": "a"})
        self.assertEqual(json.loads(back.stdout),
                         [{"t": "worker one", "s": "todo"}])

    def test_the_same_session_label_finds_its_list_again(self):
        self.run_tk("add", "step", env={"TICKMARK_SESSION": "a"})
        again = self.run_tk("go", "1", env={"TICKMARK_SESSION": "a"})
        self.assertIn("step", again.stdout)
        self.assertEqual(again.returncode, 0)

    def test_an_unset_session_still_shares_the_project_list(self):
        self.run_tk("add", "shared")
        self.assertIn("shared", self.run_tk().stdout)


# --- defect 3: removing a task reshuffles the numbers --------------------

class RemovalWarnsAboutRenumbering(Base):

    def setUp(self):
        Base.setUp(self)
        self.run_tk("add", "one", "two", "three")

    def test_removing_from_the_middle_warns(self):
        out = self.run_tk("rm", "1").stdout
        self.assertIn("Numbers were reassigned", out)
        self.assertIn("○ 1 two", out)
        self.assertIn("○ 2 three", out)

    def test_removing_the_last_task_shifts_nothing_and_stays_quiet(self):
        out = self.run_tk("rm", "3").stdout
        self.assertNotIn("Numbers were reassigned", out)

    def test_other_commands_never_warn(self):
        for args in (["go", "1"], ["ok", "1"], ["next"], ["add", "four"]):
            self.assertNotIn("Numbers were reassigned",
                             self.run_tk(*args).stdout, args)

    def test_the_warning_is_not_in_the_json_output(self):
        self.run_tk("rm", "1")
        out = self.run_tk("--json").stdout
        self.assertEqual([t["t"] for t in json.loads(out)], ["two", "three"])

    def test_display_stays_numbered_from_one(self):
        self.run_tk("rm", "1")
        numbers = [line.split()[1] for line in self.run_tk().stdout.splitlines()[1:]]
        self.assertEqual(numbers, ["1", "2"])


# --- defect 4: no colour, no fit to the terminal -------------------------

class Rendering(Base):

    def tty_render(self, tasks, **env):
        stdout = mock.MagicMock(wraps=sys.stdout)
        stdout.isatty.return_value = True
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.dict(os.environ, env, clear=False):
            return self.tk.render(tasks)

    def test_colour_on_a_terminal(self):
        out = self.tty_render([{"t": "a", "s": "todo"},
                               {"t": "b", "s": "doing"},
                               {"t": "c", "s": "done"}], COLUMNS="80", TERM="xterm")
        for state in ("todo", "doing", "done"):
            self.assertIn(self.tk.COLOR[state], out)
        self.assertTrue(out.endswith(self.tk.RESET))

    def test_no_colour_when_NO_COLOR_is_set(self):
        out = self.tty_render([{"t": "a", "s": "todo"}],
                              COLUMNS="80", TERM="xterm", NO_COLOR="1")
        self.assertNotIn("\033", out)

    def test_no_colour_on_a_dumb_terminal(self):
        out = self.tty_render([{"t": "a", "s": "todo"}],
                              COLUMNS="80", TERM="dumb")
        self.assertNotIn("\033", out)

    def test_long_subjects_are_cut_to_the_terminal_width(self):
        out = self.tty_render([{"t": "x" * 200, "s": "todo"}],
                              COLUMNS="30", TERM="dumb")
        line = out.splitlines()[1]
        self.assertLessEqual(len(line), 30)
        self.assertTrue(line.endswith("…"))

    def test_short_subjects_are_left_alone(self):
        out = self.tty_render([{"t": "short", "s": "todo"}],
                              COLUMNS="30", TERM="dumb")
        self.assertTrue(out.splitlines()[1].endswith("short"))

    def test_nothing_is_cut_when_the_output_is_redirected(self):
        long_subject = "y" * 300
        self.run_tk("add", long_subject)
        out = self.run_tk(env={"COLUMNS": ""}).stdout
        self.assertIn(long_subject, out)

    def test_redirected_output_carries_no_escape_codes(self):
        self.run_tk("add", "a", "b")
        self.run_tk("go", "1")
        for args in ([], ["ok", "1"], ["--json"], ["rm", "1"]):
            self.assertNotIn("\033", self.run_tk(*args).stdout, args)

    @unittest.skipUnless(hasattr(os, "openpty"), "no pty on this platform")
    def test_json_stays_parsable_even_on_a_terminal(self):
        self.run_tk("add", "a")
        out = self.run_pty("--json")
        self.assertNotIn("\033", out)
        self.assertEqual(json.loads(out.strip()), [{"t": "a", "s": "todo"}])

    @unittest.skipUnless(hasattr(os, "openpty"), "no pty on this platform")
    def test_the_list_is_coloured_on_a_real_terminal(self):
        self.run_tk("add", "a")
        self.assertIn("\033[", self.run_pty())
        self.assertNotIn("\033[", self.run_pty(NO_COLOR="1"))


# --- store robustness ----------------------------------------------------

class StoreRobustness(Base):

    def write_store(self, text):
        path = self.tk.state_path()
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_empty_store_reads_as_an_empty_list(self):
        self.assertEqual(self.tk.load(), [])
        result = self.run_tk()
        self.assertEqual(result.returncode, 0)
        self.assertIn("No tasks yet", result.stdout)

    def test_a_truncated_file_does_not_crash(self):
        self.write_store('[{"t": "half wri')
        self.assertEqual(self.tk.load(), [])
        self.assertEqual(self.run_tk("add", "fresh").returncode, 0)

    def test_a_zero_byte_file_does_not_crash(self):
        self.write_store("")
        self.assertEqual(self.tk.load(), [])

    def test_a_json_object_instead_of_a_list_is_ignored(self):
        self.write_store('{"t": "not a list"}')
        self.assertEqual(self.tk.load(), [])

    def test_malformed_entries_are_dropped_not_crashed_on(self):
        self.write_store(json.dumps(
            [{"t": "good", "s": "todo"}, 42, {"t": "no state"},
             {"s": "todo"}, {"t": "bad state", "s": "wat"}]))
        self.assertEqual(self.tk.load(), [{"t": "good", "s": "todo"}])
        out = self.run_tk().stdout
        self.assertIn("good", out)
        self.assertIn("Tasks 0/1", out)


# --- migration from the pre-1.0 store ------------------------------------

class LegacyMigration(Base):

    def seed_legacy(self, tasks):
        name = os.path.basename(self.tk.state_path())
        os.makedirs(self.legacy, exist_ok=True)
        with open(os.path.join(self.legacy, name), "w") as f:
            json.dump(tasks, f)
        return name

    def test_an_agy_tasks_list_is_picked_up_once(self):
        self.seed_legacy([{"t": "from agy", "s": "doing"}])
        self.assertEqual(self.tk.load(), [{"t": "from agy", "s": "doing"}])

    def test_migration_does_not_overwrite_an_existing_list(self):
        self.tk.save([{"t": "current", "s": "todo"}])
        self.seed_legacy([{"t": "from agy", "s": "todo"}])
        self.assertEqual(self.tk.load(), [{"t": "current", "s": "todo"}])

    def test_a_session_list_does_not_inherit_the_legacy_file(self):
        self.seed_legacy([{"t": "from agy", "s": "todo"}])
        self.tk.SESSION = "worker-a"
        self.assertEqual(self.tk.load(), [])


# --- the visible contract, which must not move ---------------------------

class VisibleContract(Base):

    def test_every_command_reprints_the_whole_list(self):
        self.run_tk("add", "a", "b")
        for args in (["go", "1"], ["ok", "1"], ["next"], ["add", "c"], []):
            out = self.run_tk(*args).stdout
            self.assertIn("Tasks ", out, args)
            self.assertIn(" a", out, args)

    def test_json_keys_and_states(self):
        self.run_tk("add", "a", "b", "c")
        self.run_tk("go", "2")
        self.run_tk("ok", "1")
        tasks = json.loads(self.run_tk("--json").stdout)
        self.assertEqual(tasks, [{"t": "a", "s": "done"},
                                 {"t": "b", "s": "doing"},
                                 {"t": "c", "s": "todo"}])

    def test_new_clears_the_list(self):
        self.run_tk("add", "a")
        self.assertIn("No tasks yet", self.run_tk("new").stdout)

    def test_a_bad_number_is_refused_without_touching_the_list(self):
        self.run_tk("add", "a")
        result = self.run_tk("ok", "9")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(self.run_tk("--json").stdout),
                         [{"t": "a", "s": "todo"}])

    def test_unknown_command_exits_nonzero(self):
        self.assertEqual(self.run_tk("frobnicate").returncode, 1)

    def test_version_and_help(self):
        self.assertIn("tickmark", self.run_tk("--version").stdout)
        self.assertIn("tk add", self.run_tk("--help").stdout)


if __name__ == "__main__":
    unittest.main()
