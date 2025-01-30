from sys import stdout, stderr
import logging
from pathlib import Path
from json import dumps, loads
from lark import Lark, logger, ast_utils
from lark_ambig_tools import CountTrees
from lark.exceptions import UnexpectedCharacters
from rich import print as richprint
from argparse import ArgumentParser
from io import StringIO, TextIOBase
from time import time
from typing import List

from . import VhdlParseTreeTransformers
from . import VhdlCstTransformer


# https://github.com/pypy/pypy/issues/2999#issuecomment-1906226685
def fix_pypy_console():
    stdout.reconfigure(encoding="latin-1")
    stderr.reconfigure(encoding="latin-1")
    return
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


vhdl_fileext = ["vhd", "vhdl", "vht"]
vlog_fileext = ["v", "vh", "verilog", "vlg", "vo", "vqm", "vt", "veo", "sv", "svh", "vlog"]


def filetype(fpath: Path):
    fileext = fpath.suffix[1:]
    if fileext in vhdl_fileext:
        return "VHDL"
    elif fileext in vlog_fileext:
        return "VLOG"
    else:
        return fileext.upper()


class HdlParser:
    def __init__(self, ambig=False, use_regex=True, debug=False):
        if debug:
            logger.setLevel(logging.DEBUG)
        self.vhdl_parser = VhdlParser(ambig, use_regex, debug)
        self.vlog_parser = VerilogParser(ambig, use_regex, debug)

    def parseFile(self, fpath: TextIOBase | Path | str, ftype: str = ""):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        ftype = ftype.upper()
        if isinstance(fpath, Path):
            if ftype not in ["VHDL", "VLOG"]:
                ftype = filetype(fpath)
        assert ftype in ["VHDL", "VLOG"]

        if isinstance(fpath, Path):
            txt = fpath.read_text("latin-1")
            return self.parse(txt, ftype)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            return self.parse(txt, ftype)

    def parse(self, txt: str, ftype: str = "VHDL"):
        if ftype == "VHDL":
            return self.vhdl_parser.parse(txt)
        elif ftype == "VLOG":
            return self.vlog_parser.parse(txt)
        else:
            raise ValueError(f"unknown file type {ftype}")


class VerilogParser:
    def __init__(self, ambig=False, use_regex=True, debug=False):
        try:
            import regex

            use_regex = True
        except ModuleNotFoundError:
            use_regex = False

        self.ambig = ambig

        # self.parser = Lark(
        #    open(Path(__file__).parent / "verilog.lark", encoding="latin-1"),
        #    start="design_file",
        #    regex=use_regex,
        #    debug=debug,
        #    ambiguity="explicit" if ambig else "resolve",
        #    lexer="dynamic",
        # )
        # self.csttransformer = ast_utils.create_transformer(
        #    VerilogCstTransformer, VerilogParseTreeTransformers.Tokens()
        # )

    def parseFile(self, fpath: TextIOBase | Path | str):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        if isinstance(fpath, Path):
            txt = fpath.read_text("latin-1")
            return self.parse(txt)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            return self.parse(txt)

    def parse(self, txt: str):
        raise NotImplementedError("Verilog parsing not yet supported!")


def count(tree):
    cnt = VhdlParseTreeTransformers.CountAmbig()
    cnt.visit(tree)
    print(f"ambig nodes: {cnt.cnt}")
    counted_tree = CountTrees().transform(tree)
    print(f"derivations: {counted_tree.derivation_count}")


class VhdlParser:
    def __init__(self, ambig=False, use_regex=True, debug=False):
        try:
            import regex

            use_regex = True
        except ModuleNotFoundError:
            use_regex = False

        self.ambig = ambig

        self.parser = Lark(
            open(Path(__file__).parent / "vhdl-2008.lark", encoding="latin-1"),
            start="design_file",
            regex=use_regex,
            debug=debug,
            ambiguity="explicit" if ambig else "resolve",
            lexer="dynamic",
        )
        self.csttransformer = ast_utils.create_transformer(
            VhdlCstTransformer, VhdlParseTreeTransformers.Tokens()
        )

    def parseFile(self, fpath: TextIOBase | Path | str):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        if isinstance(fpath, Path):
            txt = fpath.read_text("latin-1")
            return self.parse(txt)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            return self.parse(txt)

    def parse(self, txt: str):
        # parse code to tree
        parse_tree = self.parser.parse(txt)

        # remove and count ambiguities
        if self.ambig:
            if False:
                from colorama import Fore

                parser2 = Lark(
                    open("hdltree/vhdl-2008.lark", encoding="latin-1"),
                    start="design_file",
                    regex=True,
                )
                parse_tree2 = parser2.parse(txt)
                count(parse_tree)
                parse_tree = VhdlParseTreeTransformers.MakeAmbigUnique().transform(parse_tree)
                count(parse_tree)
                parse_tree = VhdlParseTreeTransformers.CollapseAmbig().transform(parse_tree)
                match = parse_tree == parse_tree2
                print(
                    "disambiguated tree matches: "
                    + (Fore.GREEN if match else Fore.RED)
                    + str(match)
                    + Fore.RESET
                )
            else:
                parse_tree = VhdlParseTreeTransformers.CollapseAmbig().transform(parse_tree)

        # convert parse tree to custom format
        # try:
        cst = self.csttransformer.transform(parse_tree)
        VhdlParseTreeTransformers.AddCstParent().visit(cst)
        # except VisitError as e:
        #    print(e)
        #    print(e.__context__)
        #    errjson = e.__context__.json()
        #    print(dumps(loads(errjson), indent=2))
        return cst


def is_excluded(inpath: Path, excluded: List[Path]):
    for ex in excluded:
        if inpath.is_relative_to(ex):
            return True
    return False


def main():
    parser = ArgumentParser(description="Pure Python HDL parser")
    parser.add_argument("-i", "--input", action="append", help="HDL source file or directory")
    parser.add_argument(
        "-p", "--print-tree", action="store_true", help="Print the parsed tree to stdout"
    )
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
    args, unparsed = parser.parse_known_args()
    # Allow file to be passed in without -i
    if not args.input:
        if len(unparsed) > 0:
            args.input = unparsed
        else:
            args.input = ["."]

    ve = HdlParser(ambig=args.ambig)

    args.input = [Path(f) for f in args.input]
    args.exclude = [Path(f) for f in args.exclude]

    files = []
    for inpath in args.input:
        if inpath.is_file() and not is_excluded(inpath, args.exclude):
            files.append(inpath)
        elif inpath.is_dir() and not is_excluded(inpath, args.exclude):
            for ext in vhdl_fileext:
                for infile in inpath.rglob("**/*." + ext):
                    if not is_excluded(infile, args.exclude):
                        files.append(infile)

    for f in files:
        print(f"analyzing {f}", end="", flush=True)
        prev = time()
        try:
            cst = ve.parseFile(f)
        except UnexpectedCharacters as e:
            print()
            print(f"error at line {e.line}, column {e.column}")
            print("expected:")
            print(e.allowed)
            print("from rules:")
            print(e.considered_rules)
            print()
        except Exception as e:
            print(e)

        lines = f.read_text().count("\n")
        elapsed = time() - prev
        print(
            f"\ranalyzed {f} ({lines} lines) in {elapsed:.2f} seconds ({lines/elapsed:.2f} lines/sec)"
        )

        if args.print_tree:
            richprint(cst.rich_tree())


if __name__ == "__main__":
    main()
