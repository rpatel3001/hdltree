from sys import argv
from os import getenv

from dataclasses import asdict
from yaml import dump
from json import dumps, loads

from rich import print as richprint
from re import sub

from pathlib import Path
from argparse import ArgumentParser

from colorama import Fore

from lark.exceptions import UnexpectedCharacters

from hdltree.hdltree import is_excluded
from hdltree.Parsers import HdlParser, vhdl_fileext
from hdltree.symbol import to_symbol


if __name__ == "__main__":
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
                    if infile.is_file() and not is_excluded(infile, args.exclude):
                        files.append(infile)

    for f in files:
        print(f"analyzing {f}")
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
        ##richprint(cst.rich_tree())
        ##print(cst)
        # cst.print()
        # richprint(cst)
        # print(parse_tree.pretty())
        # print(cst.pretty())
        # print(dumps(asdict(cst), indent=2))
        # print(dump(asdict(cst), default_flow_style=False))
        if getenv("RICHPRINT_CST"):
            richprint(cst.rich_tree())
        if getenv("PRINT_CST"):
            print(cst)

        txt = f.read_text("latin-1").lower()
        csttxt = str(cst).lower()

        txt = sub(r"--.*", r"", txt)
        csttxt = sub(r"--.*", r"", csttxt)

        txt = sub(r"\s+", "", txt).strip()
        csttxt = sub(r"\s+", "", csttxt).strip()

        if txt != csttxt:
            print(f"{Fore.RED}inexact recreation: {f.name}{Fore.RESET}")
            print(txt)
            print(csttxt)
        else:
            print(f"{Fore.GREEN}more or less exact recreation: {f.name}{Fore.RESET}")

        for ent in cst.entities:
            to_symbol(ent)
