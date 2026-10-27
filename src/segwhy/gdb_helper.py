"""Script run *inside* gdb by debugger.py (never imported by segwhy itself).

gdb has its own Python with a `gdb` module. This script:
  1. quiets gdb and gives the program the same environment it would have
     without segwhy,
  2. runs the program, with segwhy's real stdout/stderr,
  3. if it crashed: writes the signal, the bad address and the call stack to
     a JSON file (path in $SEGWHY_GDB_OUT) that debugger.py reads.
"""

import json
import os

import gdb  # only exists inside gdb


def setup_gdb():
    """Turn off everything gdb would print or ask, and let harmless signals through."""
    for command in (
        "set pagination off",
        "set confirm off",
        "set width 0",
        "set print thread-events off",
        "set print inferior-events off",
        "set debuginfod enabled off",
        "set disable-randomization off",
        "handle SIGPIPE nostop noprint pass",
        "handle SIGALRM nostop noprint pass",
        "handle SIGUSR1 nostop noprint pass",
        "handle SIGUSR2 nostop noprint pass",
        "handle SIGCHLD nostop noprint pass",
        "handle SIGWINCH nostop noprint pass",
    ):
        try:
            gdb.execute(command, to_string=True)
        except gdb.error:
            pass  # older gdb without this setting


def restore_environment():
    """Remove the variables segwhy and gdb added, so the program sees the
    environment segwhy was started with."""
    for name in ("SEGWHY_GDB_OUT", "SEGWHY_FDS", "SEGWHY_SHELL", "SEGWHY_HAD_LINES", "SEGWHY_HAD_COLUMNS"):
        try:
            gdb.execute("unset environment " + name, to_string=True)
        except gdb.error:
            pass
    original_shell = os.environ.get("SEGWHY_SHELL")
    try:
        if original_shell:
            gdb.execute("set environment SHELL=" + original_shell, to_string=True)
        else:
            gdb.execute("unset environment SHELL", to_string=True)
        for name in ("LINES", "COLUMNS"):  # gdb sets these, the shell usually doesn't
            if not os.environ.get("SEGWHY_HAD_" + name):
                gdb.execute("unset environment " + name, to_string=True)
    except gdb.error:
        pass


def output_redirection():
    """Shell redirection giving the program segwhy's real stdout and stderr.

    gdb's own output goes to /dev/null. segwhy passes its stdout/stderr as two
    extra descriptors ($SEGWHY_FDS); they are closed right after use so the
    program sees exactly the descriptors it would see without segwhy."""
    fds = os.environ.get("SEGWHY_FDS")
    if not fds:
        return ""
    out_fd, err_fd = fds.split(",")
    return " 1>&%s 2>&%s %s>&- %s>&-" % (out_fd, err_fd, out_fd, err_fd)


def read_signal(result):
    """Add the signal number, its code and the faulting address to `result`."""
    try:
        info = gdb.parse_and_eval("$_siginfo")
        result["signo"] = int(info["si_signo"])
        result["si_code"] = int(info["si_code"])
        try:
            result["address"] = int(info["_sifields"]["_sigfault"]["si_addr"])
        except gdb.error:
            pass  # signals without an address (SIGABRT...)
    except gdb.error as error:
        result["siginfo_error"] = str(error)
    try:
        result["sp"] = int(gdb.parse_and_eval("$sp"))
    except gdb.error:
        pass


def read_stack(limit=3000):
    """The call stack, innermost first, as a list of dicts (func, file, line, module)."""
    frames = []
    frame = gdb.newest_frame()
    while frame is not None and len(frames) < limit:
        entry = {"func": frame.name()}
        try:
            sal = frame.find_sal()
            if sal.symtab is not None and sal.line:
                entry["file"] = sal.symtab.fullname()
                entry["line"] = sal.line
        except Exception:
            pass
        try:
            entry["module"] = gdb.solib_name(frame.pc()) or gdb.current_progspace().filename
        except Exception:
            pass
        frames.append(entry)
        try:
            frame = frame.older()
        except gdb.error:
            break
    return frames


def main():
    """Run the program once and write what happened to $SEGWHY_GDB_OUT."""
    result = {"status": "unknown"}
    exit_info = {}

    def on_exit(event):
        """Called by gdb when the program ends normally."""
        if hasattr(event, "exit_code"):
            exit_info["code"] = event.exit_code
        exit_info["exited"] = True

    setup_gdb()
    gdb.events.exited.connect(on_exit)
    restore_environment()

    arguments = gdb.parameter("args") or ""
    try:
        gdb.execute("run " + arguments + output_redirection(), to_string=True)
    except gdb.error as error:
        result["error"] = str(error)

    inferior = gdb.selected_inferior()
    if exit_info.get("exited") or not inferior.pid:
        result["status"] = "exited" if exit_info.get("exited") else "failed"
        result["exit_code"] = exit_info.get("code", 0)
    else:
        result["status"] = "signal"
        read_signal(result)
        result["frames"] = read_stack()
        try:
            # Memory map, to know if the bad address was read-only (Linux only).
            with open("/proc/%d/maps" % inferior.pid) as maps:
                result["maps"] = maps.read()
        except OSError:
            pass
        try:
            gdb.execute("kill", to_string=True)
        except gdb.error:
            pass

    with open(os.environ["SEGWHY_GDB_OUT"], "w") as handle:
        json.dump(result, handle)


main()
