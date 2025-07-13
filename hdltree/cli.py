from pathlib import Path
from argparse import ArgumentParser
from typing import List
from rich.console import Console

from . import Parser
from . import Analyzer


# https://github.com/pypy/pypy/issues/2999#issuecomment-1906226685
def fix_pypy_console():
    #stdout.reconfigure(encoding="latin-1")
    #stderr.reconfigure(encoding="latin-1")
    #return
    import platform
    import sys
    import subprocess
    import re
    import os
    import io

    WINDOWS_CODEPAGES = {
        437: "ibm437",
        850: "ibm850",
        1252: "windows-1252",
        20127: "us-ascii",
        28591: "iso-8859-1",
        28592: "iso-8859-2",
        28593: "iso-8859-3",
        65000: "utf-7",
        65001: "utf-8",
    }
    # implementation note: MUST be run before the first read from stdin.
    # (stdout and sterr may be already written-to, albeit maybe corruptedly.)
    if platform.system() == "Windows":
        ##colorama.just_fix_windows_console()
        if "PYTHONIOENCODING" not in os.environ:
            if platform.python_implementation() == "PyPy":
                if isinstance(sys.stdout.buffer.raw, io.FileIO):
                    # Workaround for https://github.com/pypy/pypy/issues/2999
                    chcp_output = subprocess.check_output(["chcp.com"], encoding="ascii")
                    cur_codepage = int(re.match(r"Active code page: (\d+)", chcp_output).group(1))
                    cur_encoding = WINDOWS_CODEPAGES[cur_codepage]
                    for f in [sys.stdin, sys.stdout, sys.stderr]:
                        if f.encoding != cur_encoding:
                            f.reconfigure(encoding=cur_encoding)


def main():
    parser = ArgumentParser(description="Pure Python HDL parser")
    parser.add_argument("-i", "--input", action="append", help="HDL source file or directory")
    parser.add_argument(
        "-a",
        "--ambig",
        action="store_true",
        help="Instruct the parser to return an ambiguous tree and resolve them according to semantic rules",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        default=[],
        help="Files and directories to ignore",
    )
    parser.add_argument(
        "-f",
        "--fix-console",
        action="store_true",
        help="Fix console encoding (needed for pypy)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debugging in the analyzer",
    )
    parser.add_argument(
        "--debug_lark",
        action="store_true",
        help="Enable debugging in lark",
    )
    parser.add_argument(
        "--std",
        action="store_true",
        help="Parse and include the standard VHDL libraries (std and ieee)",
    )
    parser.add_argument(
        "--no-regex",
        action="store_false",
        help="Don't use the regex library",
    )
    parser.add_argument(
        "--cst",
        action="store_true",
        help="Print CST to console",
    )
    parser.add_argument(
        "--ast",
        action="store_true",
        help="Print AST to console",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Print simplified AST to console",
    )
    args, unparsed = parser.parse_known_args()

    if args.fix_console:
        fix_pypy_console()

    # Allow file to be passed in without -i
    if not args.input:
        if len(unparsed) > 0:
            args.input = unparsed
        else:
            args.input = ["."]

    args.input = [Path(f) for f in args.input]
    args.exclude = [Path(f) for f in args.exclude]

    files = Parser.collect_files(args.input, args.exclude)

    proj = Analyzer.Project(args.ambig, args.no_regex, debug_lark=args.debug_lark, add_std=args.std)
    proj.add_library("src")
    for f in files:
        proj.add_file("src", f, args.cst, args.debug)

    if args.ast:
        print()
        con = Console(emoji=False)
        con.print(proj.rich_tree())

    if args.simple:
        print()
        proj.print_simple()

if __name__ == "__main__":
    main()
