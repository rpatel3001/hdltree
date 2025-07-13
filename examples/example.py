from re import sub

from pathlib import Path
from argparse import ArgumentParser

from colorama import Fore

from hdltree.symbol import to_symbol

from hdltree import Parser, Analyzer


if __name__ == "__main__":
    parser = ArgumentParser(description="Pure Python HDL parser")
    parser.add_argument("-i", "--input", action="append", help="HDL source file or directory")
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

    args.input = [Path(f) for f in args.input]
    args.exclude = [Path(f) for f in args.exclude]

    files = Parser.collect_files(args.input, args.exclude)
    proj = Analyzer.Project()
    proj.add_library("src")

    for f in files:
        cst = proj.add_file("src", f)

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
