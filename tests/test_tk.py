"""Tests for tk. Standard library only, same as the tool itself.

Run with: python3 -m unittest discover -s tests -v
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TK = os.path.join(ROOT, "tk")
TK_STATUS = os.path.join(ROOT, "integrations", "tk-status.py")

# Any of the four scales the duration can print, anchored at end of line.
DURATION = re.compile(r"(\d+s|\d+m\d\ds|\d+h\d\dm|\d+d\d\dh)$")


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


# --- defect: a glyph the console refused killed the whole command --------
#
# Reported from the same Windows install: on code page 1252 the marks raise
# UnicodeEncodeError, the command dies, and the status line reading it goes
# blank with nothing to explain why.

class OutputEncoding(Base):

    def test_a_cp1252_stream_refuses_the_marks(self):
        """The platform fact the fix exists for, so it is not testing thin air."""
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with self.assertRaises(UnicodeEncodeError):
            stream.write(self.tk.MARK["doing"])
            stream.flush()

    def test_a_narrow_console_no_longer_stops_the_command(self):
        self.run_tk("add", "Générer les CVs adaptés")
        for encoding in ("cp1252", "ascii", "latin-1"):
            out = self.run_tk("go", "1", env={"PYTHONIOENCODING": encoding})
            self.assertEqual(out.returncode, 0, encoding)
            self.assertIn("Tasks 0/1", out.stdout, encoding)
            self.assertEqual(out.stderr, "", encoding)

    def test_the_marks_still_come_out_as_utf8(self):
        self.run_tk("add", "a")
        out = self.run_tk("go", "1", env={"PYTHONIOENCODING": "cp1252"})
        self.assertIn("\u25b8", out.stdout)

    def test_an_error_message_survives_the_same_console(self):
        out = self.run_tk("frobnicate", env={"PYTHONIOENCODING": "cp1252"})
        self.assertEqual(out.returncode, 1)
        self.assertIn("Unknown command", out.stderr)

    def test_a_stream_that_cannot_take_the_marks_falls_back_to_ascii(self):
        stream = mock.MagicMock()
        stream.encoding = "cp1252"
        stream.reconfigure.side_effect = AttributeError("no reconfigure here")
        with mock.patch.object(sys, "stdout", stream), \
                mock.patch.object(sys, "stderr", stream):
            self.tk.setup_output()
        self.assertTrue(self.tk.ASCII)

    def test_a_stream_that_takes_utf8_keeps_the_marks(self):
        stream = mock.MagicMock()
        stream.encoding = "utf-8"
        with mock.patch.object(sys, "stdout", stream), \
                mock.patch.object(sys, "stderr", stream):
            self.tk.setup_output()
        self.assertFalse(self.tk.ASCII)

    def test_a_stream_with_no_encoding_of_its_own_keeps_the_marks(self):
        # io.StringIO, a test capture: takes any text, not a reason to degrade.
        self.assertTrue(self.tk.encodable("✔…▸", io.StringIO()))

    def test_the_ascii_list_says_the_same_thing(self):
        tasks = [{"t": "lire le config", "s": "done"},
                 {"t": "patcher", "s": "doing", "since": BASE - 134},
                 {"t": "tester", "s": "todo"}]
        with mock.patch.object(self.tk, "ASCII", True), \
                mock.patch.dict(os.environ,
                                {"COLUMNS": "80", "NO_COLOR": "1",
                                 "TERM": "dumb"}, clear=False):
            out = self.tk.render(tasks, now=BASE)
        self.assertEqual(out.splitlines(), [
            "Tasks 1/3",
            "x 1 lire le config",
            "> 2 patcher  2m14s",
            "o 3 tester"])
        self.assertTrue(out.isascii())

    def test_the_ascii_ellipsis_is_counted_in_the_truncation(self):
        with mock.patch.object(self.tk, "ASCII", True), \
                mock.patch.dict(os.environ,
                                {"COLUMNS": "20", "NO_COLOR": "1",
                                 "TERM": "dumb"}, clear=False):
            line = self.tk.render([{"t": "z" * 80, "s": "todo"}]).splitlines()[1]
        self.assertEqual(len(line), 20)
        self.assertTrue(line.endswith("..."), line)

    def test_the_json_stays_valid_when_the_console_is_ascii_only(self):
        with mock.patch.object(self.tk, "ASCII", True):
            payload = json.dumps([{"t": "Générer", "s": "todo"}],
                                 ensure_ascii=self.tk.ASCII)
        self.assertTrue(payload.isascii())
        self.assertEqual(json.loads(payload)[0]["t"], "Générer")

    def test_emit_never_raises_on_a_character_the_stream_refuses(self):
        class Refuses(io.StringIO):
            encoding = "ascii"

            def write(self, text):
                text.encode("ascii")  # raises, exactly as a cp1252 stream does
                return io.StringIO.write(self, text)

        stream = Refuses()
        self.tk.emit("✔ 1 Générer", stream)  # must not raise
        self.assertIn("1 G", stream.getvalue())


# --- defect: the project root fell apart without git ---------------------
#
# Reported from a Windows 11 / PowerShell install where git was not on the
# PATH: the list re-forked every time the agent stepped into a subdirectory,
# because os.getcwd() was the whole fallback.

class ProjectRootWithoutGit(Base):

    def setUp(self):
        Base.setUp(self)
        # os.getcwd() resolves symlinks and the temp directory may be one, so
        # compare against the resolved path or the assertion tests the symlink.
        self.work = os.path.realpath(self.work)
        self.sub = os.path.join(self.work, "src", "deep")
        os.makedirs(self.sub)

    def no_git(self, **extra):
        """An environment with no git to be found anywhere on the PATH."""
        e = {"PATH": os.path.join(self.tmp, "empty-path")}
        e.update(extra)
        return e

    def run_in(self, where, *args, **kwargs):
        return subprocess.run(
            [sys.executable, TK] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, cwd=where,
            env=self.env(**kwargs.pop("env", {})), **kwargs)

    def test_a_marker_file_identifies_the_root_when_git_is_missing(self):
        open(os.path.join(self.work, "pyproject.toml"), "w").close()
        with mock.patch.dict(os.environ, self.no_git(), clear=False):
            os.chdir(self.sub)
            self.assertEqual(self.tk.project_root(), self.work)

    def test_every_marker_counts(self):
        for marker in self.tk.MARKERS:
            target = os.path.join(self.work, marker)
            os.makedirs(target) if marker in (".git", ".hg") else \
                open(target, "w").close()
            self.assertEqual(self.tk.marker_root(self.sub), self.work, marker)
            shutil.rmtree(target, True)
            if os.path.exists(target):
                os.remove(target)

    def test_no_marker_anywhere_falls_back_to_the_working_directory(self):
        with mock.patch.dict(os.environ, self.no_git(), clear=False):
            os.chdir(self.sub)
            self.assertEqual(self.tk.project_root(), self.sub)

    def test_the_nearest_marker_wins_over_a_farther_one(self):
        open(os.path.join(self.work, "package.json"), "w").close()
        middle = os.path.dirname(self.sub)
        open(os.path.join(middle, "pyproject.toml"), "w").close()
        self.assertEqual(self.tk.marker_root(self.sub), middle)

    def test_the_walk_stops_at_the_filesystem_root(self):
        # It must terminate rather than loop on "/" forever.
        self.assertIn(self.tk.marker_root(os.sep), ("", os.sep))

    def test_end_to_end_a_subdirectory_shares_the_list_without_git(self):
        open(os.path.join(self.work, "pyproject.toml"), "w").close()
        self.run_in(self.work, "add", "a", env=self.no_git())
        out = self.run_in(self.sub, "add", "b", env=self.no_git())
        self.assertEqual(out.returncode, 0)
        self.assertIn("Tasks 0/2", out.stdout)
        self.assertIn(" a", out.stdout)

    def test_the_old_behaviour_is_what_broke(self):
        # Without the walk, the same two calls land in two different files.
        open(os.path.join(self.work, "pyproject.toml"), "w").close()
        with mock.patch.dict(os.environ, self.no_git(), clear=False):
            os.chdir(self.sub)
            self.assertNotEqual(self.tk.cwd(), self.tk.project_root())

    def test_a_deleted_working_directory_does_not_crash(self):
        with mock.patch.object(self.tk.os, "getcwd",
                               side_effect=OSError("gone")):
            self.assertEqual(self.tk.cwd(), self.tk.HOME)


class ProjectRootOverride(Base):
    """TICKMARK_ROOT: the only answer a wandering working directory cannot move."""

    def test_it_wins_over_git_and_over_the_walk(self):
        pinned = os.path.join(self.tmp, "pinned")
        os.makedirs(pinned)
        self.tk.ROOT_OVERRIDE = pinned
        self.assertEqual(self.tk.project_root(), pinned)

    def test_the_list_follows_the_pin_from_anywhere(self):
        pinned = os.path.join(self.tmp, "pinned")
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(pinned)
        os.makedirs(elsewhere)
        self.run_tk("add", "a", env={"TICKMARK_ROOT": pinned})
        out = subprocess.run(
            [sys.executable, TK, "--json"], stdout=subprocess.PIPE,
            universal_newlines=True, cwd=elsewhere,
            env=self.env(TICKMARK_ROOT=pinned))
        self.assertEqual([t["t"] for t in json.loads(out.stdout)], ["a"])

    def test_a_relative_pin_is_resolved_once_not_re_resolved_per_call(self):
        # Two calls from two directories must hash to the same file.
        e = dict(os.environ)
        e["TICKMARK_ROOT"] = "~"
        with mock.patch.dict(os.environ, e, clear=True):
            module = import_tk()
        self.assertEqual(module.ROOT_OVERRIDE, os.path.expanduser("~"))


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

    # The additive keys, so the assertions below state a contract instead of a
    # frozen shape: "t" and "s" are the contract, the rest rides on top.
    EXTRA = ("since", "elapsed_seconds", "agent")

    def core(self, tasks):
        return [{k: v for k, v in t.items() if k not in self.EXTRA}
                for t in tasks]

    def test_json_keys_and_states(self):
        self.run_tk("add", "a", "b", "c")
        self.run_tk("go", "2")
        self.run_tk("ok", "1")
        tasks = json.loads(self.run_tk("--json").stdout)
        self.assertEqual(self.core(tasks),
                         [{"t": "a", "s": "done"},
                          {"t": "b", "s": "doing"},
                          {"t": "c", "s": "todo"}])
        # Which task is allowed which extra key: only the one in progress is
        # running, only one that actually ran has a duration to keep, and "a"
        # was ticked off without ever being started.
        self.assertEqual([sorted(set(t) - {"t", "s"}) for t in tasks],
                         [[], ["since"], []])

    def test_a_task_that_ran_keeps_its_duration_and_nothing_else_moves(self):
        self.run_tk("add", "a", "b")
        self.run_tk("go", "1")
        self.run_tk("ok", "1")
        tasks = json.loads(self.run_tk("--json").stdout)
        self.assertEqual(self.core(tasks),
                         [{"t": "a", "s": "done"}, {"t": "b", "s": "todo"}])
        self.assertEqual(sorted(set(tasks[0]) - {"t", "s"}), ["elapsed_seconds"])
        self.assertNotIn("since", tasks[0])

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


# --- the duration on the step in progress --------------------------------
#
# The rendered output now depends on the clock, so nothing here reads the real
# one: unit tests pass `now` in, end-to-end tests write a `since` far enough in
# the past that the printed value cannot change while the test runs. No sleeps.

BASE = 1_700_000_000  # a fixed "now" for the unit tests


class DurationFormat(Base):
    """The scale, and what happens to values that are not a duration."""

    def at(self, seconds_ago):
        return self.tk.elapsed(BASE - seconds_ago, BASE)

    def test_the_four_scales(self):
        self.assertEqual(self.at(0), "0s")
        self.assertEqual(self.at(1), "1s")
        self.assertEqual(self.at(59), "59s")
        self.assertEqual(self.at(60), "1m00s")
        self.assertEqual(self.at(134), "2m14s")
        self.assertEqual(self.at(3599), "59m59s")
        self.assertEqual(self.at(3600), "1h00m")
        self.assertEqual(self.at(3600 * 8 + 60 * 7), "8h07m")
        self.assertEqual(self.at(86399), "23h59m")
        self.assertEqual(self.at(86400), "1d00h")
        self.assertEqual(self.at(86400 * 2 + 3600 * 4), "2d04h")

    def test_it_stays_five_or_six_characters_wide(self):
        # The leading number is not padded — "2m14s", the shape that was
        # validated, not "02m14s" — so the width gains one character when it
        # gains a digit, once per scale. The trailing number is padded, which
        # is what would otherwise make it wobble every ten seconds.
        for seconds in (60, 134, 599, 600, 3599, 3600, 3600 * 12, 86399,
                        86400, 86400 * 9, 86400 * 40):
            self.assertIn(len(self.at(seconds)), (5, 6), seconds)

    def test_the_trailing_number_is_padded_so_it_never_wobbles(self):
        self.assertEqual(self.at(60), "1m00s")
        self.assertEqual(self.at(69), "1m09s")
        self.assertEqual(self.at(3600 * 3 + 60 * 7), "3h07m")
        self.assertEqual(self.at(86400 + 3600 * 2), "1d02h")

    def test_a_clock_that_went_backwards_reads_as_zero(self):
        self.assertEqual(self.tk.elapsed(BASE + 500, BASE), "0s")

    def test_anything_that_is_not_a_number_shows_no_duration(self):
        for bad in (None, "", "1700000000", True, False, [], {}, float("nan"),
                    float("inf")):
            self.assertEqual(self.tk.elapsed(bad, BASE), "", repr(bad))


class DurationRendering(Base):
    """Where it lands on the line, and what gives way when it does not fit."""

    def plain(self, tasks, now=BASE, **env):
        e = {"COLUMNS": "80", "NO_COLOR": "1", "TERM": "dumb"}
        e.update(env)
        with mock.patch.dict(os.environ, e, clear=False):
            return self.tk.render(tasks, now=now)

    def three_steps(self, since=BASE - 134):
        doing = {"t": "patcher le handler", "s": "doing"}
        if since is not None:
            doing["since"] = since
        return [{"t": "lire le config", "s": "done"}, doing,
                {"t": "lancer les tests", "s": "todo"}]

    def test_it_lands_at_the_end_of_the_line_in_progress(self):
        lines = self.plain(self.three_steps()).splitlines()
        self.assertEqual(lines[2], "\u25b8 2 patcher le handler  2m14s")

    def test_no_other_line_carries_one(self):
        lines = self.plain(self.three_steps()).splitlines()
        self.assertEqual(lines[1], "\u2714 1 lire le config")
        self.assertEqual(lines[3], "\u25cb 3 lancer les tests")

    def test_it_costs_no_extra_line(self):
        with_duration = self.plain(self.three_steps())
        without = self.plain(self.three_steps(since=None))
        self.assertEqual(len(with_duration.splitlines()),
                         len(without.splitlines()))
        self.assertEqual(len(with_duration.splitlines()), 4)

    def test_a_todo_task_carrying_a_stray_since_stays_silent(self):
        # Only the step in progress has a "running since" to report.
        out = self.plain([{"t": "not started", "s": "todo", "since": BASE - 900}])
        self.assertEqual(out.splitlines()[1], "\u25cb 1 not started")

    def test_the_duration_is_counted_in_the_truncation(self):
        out = self.plain([{"t": "x" * 200, "s": "doing", "since": BASE - 134}],
                         COLUMNS="40")
        line = out.splitlines()[1]
        self.assertEqual(len(line), 40)
        self.assertTrue(line.endswith("  2m14s"), line)
        self.assertIn("\u2026  2m14s", line)  # the subject was cut, not the duration

    def test_it_is_never_cut_in_half(self):
        for columns in range(10, 61):
            line = self.plain(self.three_steps(),
                              COLUMNS=str(columns)).splitlines()[2]
            self.assertLessEqual(len(line), columns, columns)
            if "2m14s" not in line:
                # Gone whole: no orphan fragment of it left behind.
                for fragment in ("2m1", "m14s", "2m", "14s"):
                    self.assertNotIn(fragment, line, (columns, line))

    def test_a_terminal_too_narrow_drops_the_duration_not_the_subject(self):
        line = self.plain(self.three_steps(), COLUMNS="18").splitlines()[2]
        self.assertNotIn("2m14s", line)
        self.assertTrue(line.startswith("\u25b8 2 patcher"), line)
        self.assertLessEqual(len(line), 18)

    def test_it_survives_down_to_the_last_column_that_fits(self):
        # Head 4 + gap 2 + "2m14s" 5 + MIN_SUBJECT 8 = 19.
        self.assertIn("2m14s", self.plain(self.three_steps(), COLUMNS="19"))
        self.assertNotIn("2m14s", self.plain(self.three_steps(), COLUMNS="18"))

    def test_redirected_output_keeps_it_and_cuts_nothing(self):
        out = self.plain(self.three_steps(), COLUMNS="")
        self.assertIn("\u25b8 2 patcher le handler  2m14s", out)

    def test_it_is_inside_the_colour_of_its_line(self):
        stdout = mock.MagicMock(wraps=sys.stdout)
        stdout.isatty.return_value = True
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.dict(os.environ, {"COLUMNS": "80", "TERM": "xterm"},
                                clear=False):
            os.environ.pop("NO_COLOR", None)
            line = self.tk.render(self.three_steps(), now=BASE).splitlines()[2]
        self.assertTrue(line.startswith(self.tk.COLOR["doing"]))
        self.assertTrue(line.endswith("2m14s" + self.tk.RESET))


class DurationOnOlderLists(Base):
    """A list written before this existed must render exactly as it used to."""

    def test_a_doing_task_without_a_since_shows_no_duration(self):
        self.tk.save([{"t": "a", "s": "done"}, {"t": "b", "s": "doing"}])
        out = self.run_tk()
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.splitlines()[2], "\u25b8 2 b")
        self.assertNotRegex(out.stdout, DURATION)

    def test_the_json_of_an_older_list_is_unchanged(self):
        self.tk.save([{"t": "b", "s": "doing"}])
        self.assertEqual(json.loads(self.run_tk("--json").stdout),
                         [{"t": "b", "s": "doing"}])

    def test_an_unreadable_since_is_ignored_rather_than_raised(self):
        self.tk.save([{"t": "b", "s": "doing", "since": "yesterday"}])
        out = self.run_tk()
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.splitlines()[1], "\u25b8 1 b")

    def test_go_starts_a_clock_on_a_task_left_running_by_an_older_tk(self):
        self.tk.save([{"t": "b", "s": "doing"}])
        self.run_tk("go", "1")
        self.assertIn("since", json.loads(self.run_tk("--json").stdout)[0])


class DurationLifecycle(Base):
    """When the clock starts, when it keeps running, when it is thrown away."""

    def tasks(self):
        return json.loads(self.run_tk("--json").stdout)

    def setUp(self):
        Base.setUp(self)
        self.run_tk("add", "a", "b", "c")

    def test_go_starts_the_clock(self):
        self.run_tk("go", "2")
        a, b, c = self.tasks()
        self.assertIsInstance(b["since"], int)
        self.assertLessEqual(abs(b["since"] - time.time()), 5)
        self.assertNotIn("since", a)
        self.assertNotIn("since", c)

    def test_go_on_the_task_already_running_does_not_restart_it(self):
        self.run_tk("go", "2")
        started = self.tasks()[1]["since"]
        # Rewind it by an hour, then re-state the same step: the stall has to
        # survive, otherwise an agent repeating `tk go` hides it for good.
        self.seed_since(1, started - 3600)
        self.run_tk("go", "2")
        self.assertEqual(self.tasks()[1]["since"], started - 3600)

    def test_moving_on_drops_the_stamp_of_the_task_left_behind(self):
        self.run_tk("go", "1")
        self.run_tk("go", "3")
        tasks = self.tasks()
        self.assertEqual(tasks[0]["s"], "todo")
        self.assertNotIn("since", tasks[0])
        self.assertIn("since", tasks[2])

    def test_a_task_picked_up_again_gets_a_fresh_clock(self):
        self.run_tk("go", "1")
        self.seed_since(0, int(time.time()) - 86400)
        self.run_tk("go", "2")   # 1 goes back to todo, losing its stamp
        self.run_tk("go", "1")   # and starts from now, not from yesterday
        self.assertLessEqual(abs(self.tasks()[0]["since"] - time.time()), 5)

    def test_ok_throws_the_stamp_away(self):
        self.run_tk("go", "2")
        self.run_tk("ok", "2")
        self.assertNotIn("since", self.tasks()[1])

    def test_next_closes_one_clock_and_opens_the_following_one(self):
        self.run_tk("go", "1")
        self.run_tk("next")
        a, b, c = self.tasks()
        self.assertEqual((a["s"], b["s"]), ("done", "doing"))
        self.assertNotIn("since", a)
        self.assertIn("since", b)

    def test_only_ever_one_stamp_in_the_list(self):
        for args in (["go", "1"], ["go", "2"], ["next"], ["ok", "3"],
                     ["go", "1"], ["rm", "2"]):
            self.run_tk(*args)
            self.assertLessEqual(
                sum(1 for t in self.tasks() if "since" in t), 1, args)

    def test_the_json_stays_parsable_and_free_of_escape_codes(self):
        self.run_tk("go", "2")
        out = self.run_tk("--json").stdout
        self.assertNotIn("\033", out)
        self.assertIsInstance(json.loads(out), list)

    @unittest.skipUnless(hasattr(os, "openpty"), "no pty on this platform")
    def test_the_json_stays_clean_on_a_real_terminal_too(self):
        self.run_tk("go", "2")
        out = self.run_pty("--json")
        self.assertNotIn("\033", out)
        self.assertEqual(json.loads(out.strip())[1]["s"], "doing")

    def test_end_to_end_the_current_step_shows_its_duration(self):
        self.run_tk("go", "2")
        # Eight hours back: the printed value cannot change under this test.
        self.seed_since(1, int(time.time()) - 3600 * 8 - 60 * 7)
        lines = self.run_tk().stdout.splitlines()
        self.assertEqual(lines[2], "\u25b8 2 b  8h07m")
        self.assertEqual(lines[1], "\u25cb 1 a")
        self.assertEqual(lines[3], "\u25cb 3 c")

    def seed_since(self, index, value):
        tasks = self.tk.load()
        tasks[index]["since"] = value
        self.tk.save(tasks)


class DurationKept(Base):
    """What a task took is written down when it closes, not thrown away.

    Measured over a real agent session: eight rendered durations out of eight
    read 0s, because an agent calls tk at transitions only and no render ever
    catches a step part-way through. The live duration was correct and useless.
    """

    def setUp(self):
        Base.setUp(self)
        self.run_tk("add", "a", "b", "c")

    def tasks(self):
        return json.loads(self.run_tk("--json").stdout)

    def start(self, index, seconds_ago):
        """Put task `index` in progress, started `seconds_ago` ago."""
        self.run_tk("go", str(index + 1))
        tasks = self.tk.load()
        tasks[index]["since"] = int(time.time()) - seconds_ago
        self.tk.save(tasks)

    def test_ok_keeps_how_long_the_task_ran(self):
        self.start(0, 134)
        self.run_tk("ok", "1")
        self.assertEqual(self.tasks()[0]["elapsed_seconds"], 134)

    def test_next_keeps_it_too(self):
        self.start(0, 3600 * 2 + 60 * 7)
        self.run_tk("next")
        a, b, _ = self.tasks()
        self.assertEqual(a["elapsed_seconds"], 3600 * 2 + 60 * 7)
        self.assertEqual(b["s"], "doing")

    def test_the_running_stamp_is_still_dropped(self):
        self.start(0, 60)
        self.run_tk("ok", "1")
        self.assertNotIn("since", self.tasks()[0])

    def test_a_task_ticked_off_without_being_started_keeps_nothing(self):
        self.run_tk("ok", "1")
        self.assertNotIn("elapsed_seconds", self.tasks()[0])

    def test_an_unreadable_stamp_records_nothing_rather_than_garbage(self):
        self.tk.save([{"t": "a", "s": "doing", "since": "yesterday"}])
        self.run_tk("ok", "1")
        task = self.tasks()[0]
        self.assertEqual(task["s"], "done")
        self.assertNotIn("elapsed_seconds", task)

    def test_ticking_a_finished_task_again_does_not_wipe_its_duration(self):
        self.start(0, 134)
        self.run_tk("ok", "1")
        self.run_tk("ok", "1")
        self.assertEqual(self.tasks()[0]["elapsed_seconds"], 134)

    def test_a_finished_task_shows_what_it_took(self):
        self.start(0, 134)
        self.run_tk("ok", "1")
        self.assertEqual(self.run_tk().stdout.splitlines()[1],
                         "\u2714 1 a  2m14s")

    def test_it_costs_no_extra_line(self):
        self.start(0, 134)
        self.assertEqual(len(self.run_tk("ok", "1").stdout.splitlines()), 4)

    def test_the_duration_is_read_from_the_store_not_the_clock(self):
        # Unlike the live one, it must not move between two reprints.
        self.tk.save([{"t": "a", "s": "done", "elapsed_seconds": 134}])
        first = self.run_tk().stdout
        second = self.run_tk().stdout
        self.assertEqual(first, second)
        self.assertIn("2m14s", first)

    def test_a_corrupt_recorded_duration_prints_the_line_without_it(self):
        for bad in ("soon", None, True, [], {}, float("nan"), float("inf")):
            self.tk.save([{"t": "a", "s": "done", "elapsed_seconds": bad}])
            out = self.run_tk()
            self.assertEqual(out.returncode, 0, repr(bad))
            self.assertEqual(out.stdout.splitlines()[1], "\u2714 1 a", repr(bad))

    def test_a_todo_task_carrying_a_stray_duration_stays_silent(self):
        self.tk.save([{"t": "a", "s": "todo", "elapsed_seconds": 134}])
        self.assertEqual(self.run_tk().stdout.splitlines()[1], "\u25cb 1 a")

    def test_an_older_store_reads_and_renders_exactly_as_it_did(self):
        self.tk.save([{"t": "a", "s": "done"}, {"t": "b", "s": "doing"}])
        out = self.run_tk()
        self.assertEqual(out.stdout.splitlines()[1:],
                         ["\u2714 1 a", "\u25b8 2 b"])
        self.assertEqual(json.loads(self.run_tk("--json").stdout),
                         [{"t": "a", "s": "done"}, {"t": "b", "s": "doing"}])


class Stats(Base):
    """tk stats: the point of keeping the durations at all."""

    def seed(self, *durations):
        self.tk.save([{"t": "t%d" % i, "s": "done", "elapsed_seconds": d}
                      for i, d in enumerate(durations)])

    def line(self):
        out = self.run_tk("stats")
        self.assertEqual(out.returncode, 0)
        return out.stdout.splitlines()[-1]

    def test_it_reports_count_total_median_and_slowest(self):
        self.seed(60, 134, 3600)
        self.assertEqual(self.line(), "3 done in 1h03m | median 2m14s "
                                      "| slowest 1h00m")

    def test_an_even_count_takes_the_middle_of_the_two_middles(self):
        self.seed(60, 100, 200, 3600)
        self.assertIn("median 2m30s", self.line())

    def test_it_reprints_the_list_like_every_other_command(self):
        self.seed(134)
        out = self.run_tk("stats").stdout
        self.assertIn("Tasks 1/1", out)
        self.assertIn("t0", out)

    def test_a_list_with_nothing_finished_says_so_instead_of_lying(self):
        self.run_tk("add", "a")
        self.assertEqual(self.line(), "No recorded duration yet.")

    def test_an_older_store_says_so_too_rather_than_reporting_zero(self):
        self.tk.save([{"t": "a", "s": "done"}])
        self.assertEqual(self.line(), "No recorded duration yet.")

    def test_unfinished_tasks_are_not_counted(self):
        self.tk.save([{"t": "a", "s": "done", "elapsed_seconds": 134},
                      {"t": "b", "s": "todo", "elapsed_seconds": 99999},
                      {"t": "c", "s": "doing", "elapsed_seconds": 99999}])
        self.assertIn("1 done in 2m14s", self.line())

    def test_corrupt_durations_are_skipped_not_crashed_on(self):
        self.tk.save([{"t": "a", "s": "done", "elapsed_seconds": 134},
                      {"t": "b", "s": "done", "elapsed_seconds": "ages"}])
        self.assertIn("1 done in 2m14s", self.line())

    def test_an_empty_list_is_not_an_error(self):
        out = self.run_tk("stats")
        self.assertEqual(out.returncode, 0)
        self.assertIn("No tasks yet", out.stdout)

    def test_it_does_not_write_to_the_store(self):
        self.seed(134)
        path = self.tk.state_path()
        with open(path) as f:
            before = f.read()
        self.run_tk("stats")
        with open(path) as f:
            self.assertEqual(f.read(), before)

    def test_the_french_line(self):
        self.seed(134)
        out = self.run_tk("stats", env={"LC_ALL": "fr_FR.UTF-8"})
        self.assertIn("1 terminees en 2m14s", out.stdout)


class WholeSeconds(Base):
    """The one validator both durations go through."""

    def test_it_reads_a_number(self):
        self.assertEqual(self.tk.whole_seconds(134), 134)
        self.assertEqual(self.tk.whole_seconds(134.9), 134)

    def test_a_negative_value_reads_as_zero(self):
        self.assertEqual(self.tk.whole_seconds(-500), 0)

    def test_anything_that_is_not_a_number_reads_as_none(self):
        for bad in (None, "", "134", True, False, [], {}, float("nan"),
                    float("inf")):
            self.assertIsNone(self.tk.whole_seconds(bad), repr(bad))

    def test_format_duration_takes_a_count_straight(self):
        self.assertEqual(self.tk.format_duration(134), "2m14s")
        self.assertEqual(self.tk.format_duration(0), "0s")
        self.assertEqual(self.tk.format_duration("soon"), "")


class StatusLineDuration(Base):
    """integrations/tk-status.py: same duration, and never an error."""

    def setUp(self):
        Base.setUp(self)
        spec = importlib.util.spec_from_file_location("tk_status", TK_STATUS)
        self.status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.status)
        self.status.STORE = self.store

    def run_status(self):
        """main() with the working directory passed as an argument."""
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["tk-status.py", self.work]), \
                contextlib.redirect_stdout(out):
            code = self.status.main()
        return code, out.getvalue()

    def test_the_duration_is_appended_to_the_current_task(self):
        self.assertEqual(
            self.status.render([{"t": "a", "s": "done"},
                                {"t": "patcher le handler", "s": "doing",
                                 "since": BASE - 134}], now=BASE),
            "1/2 \u25b8 patcher le handler 2m14s")

    def test_a_task_not_in_progress_gets_none(self):
        self.assertEqual(
            self.status.render([{"t": "a", "s": "todo", "since": BASE - 134}],
                               now=BASE),
            "0/1 \u25cb a")

    def test_an_older_list_renders_as_it_did(self):
        self.assertEqual(
            self.status.render([{"t": "a", "s": "doing"}], now=BASE),
            "0/1 \u25b8 a")

    def test_an_unreadable_timestamp_prints_the_line_without_it(self):
        for bad in ("soon", None, True, [], float("nan")):
            self.assertEqual(
                self.status.render([{"t": "a", "s": "doing", "since": bad}],
                                   now=BASE),
                "0/1 \u25b8 a", repr(bad))

    def test_the_label_is_still_truncated_and_the_duration_survives(self):
        out = self.status.render(
            [{"t": "z" * 80, "s": "doing", "since": BASE - 134}], now=BASE)
        self.assertTrue(out.endswith("\u2026 2m14s"), out)

    def test_end_to_end_against_a_real_store(self):
        self.tk.save([{"t": "b", "s": "doing",
                       "since": int(time.time()) - 3600 * 8 - 60 * 7}])
        code, out = self.run_status()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "0/1 \u25b8 b 8h07m")

    def test_no_store_is_silence_and_a_zero_exit(self):
        code, out = self.run_status()
        self.assertEqual((code, out), (0, ""))

    def test_corrupt_json_is_silence_and_a_zero_exit(self):
        path = self.tk.state_path()
        with open(path, "w") as f:
            f.write('[{"t": "half writ')
        code, out = self.run_status()
        self.assertEqual((code, out), (0, ""))

    def test_a_corrupt_timestamp_never_reaches_the_status_line_as_an_error(self):
        self.tk.save([{"t": "b", "s": "doing", "since": {"not": "a time"}}])
        code, out = self.run_status()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "0/1 \u25b8 b")


if __name__ == "__main__":
    unittest.main()
