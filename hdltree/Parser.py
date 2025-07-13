import logging
from io import TextIOBase
from pathlib import Path
from lark import Lark, logger, ast_utils
from lark_ambig_tools import CountTrees
from typing import List

from . import VhdlParseTreeTransformers
from . import VhdlCstTransformer


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


def collect_files(include: List[Path], exclude: List[Path]):
    def is_excluded(test: Path):
        for ex in exclude:
            if inpath.is_relative_to(ex):
                return True
        return False

    files = []
    for inpath in include:
        if inpath.is_file() and not is_excluded(inpath):
            files.append(inpath)
        elif inpath.is_dir() and not is_excluded(inpath):
            for ext in vhdl_fileext:
                for infile in inpath.rglob("*." + ext):
                    if infile.is_file() and not is_excluded(infile):
                        files.append(infile)
    return files


def count(tree):
    cnt = VhdlParseTreeTransformers.CountAmbig()
    cnt.visit(tree)
    print(f"ambig nodes: {cnt.cnt}")
    counted_tree = CountTrees().transform(tree)
    print(f"derivations: {counted_tree.derivation_count}")


class HdlParser:
    def __init__(self, ambig=False, use_regex=True, debug=False):
        if debug:
            logger.setLevel(logging.DEBUG)

        if use_regex:
            try:
                import regex
            except ModuleNotFoundError:
                logger.warning("regex lib requested but not available")
                use_regex = False

        self.ambig = ambig

        self.vhdl_parser = Lark(
            open(Path(__file__).parent / "vhdl-2008.lark", encoding="latin-1"),
            start="design_file",
            regex=use_regex,
            debug=debug,
            ambiguity="explicit",
            lexer="dynamic",
            propagate_positions=True,
        )
        self.vhdl_transformer = ast_utils.create_transformer(
            VhdlCstTransformer, VhdlParseTreeTransformers.Tokens()
        )

        self.vlog_parser = None

    def parse_file(self, fpath: TextIOBase | Path | str, ftype: str = ""):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        ftype = ftype.upper()
        if isinstance(fpath, Path):
            if ftype not in ["VHDL", "VLOG"]:
                ftype = filetype(fpath)
        assert ftype in ["VHDL", "VLOG"]

        if isinstance(fpath, Path):
            txt = fpath.read_text("latin-1")
            p = self.parse(txt, ftype)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            p = self.parse(txt, ftype)
        p.path = fpath
        return p

    def parse(self, txt: str, ftype: str):
        if ftype == "VHDL":
            return self.parse_vhdl(txt)
        elif ftype == "VLOG":
            return self.parse_vlog(txt)
        else:
            raise ValueError(f"unknown file type {ftype}")

    def parse_vhdl(self, txt: str):
        # parse code to tree
        parse_tree = self.vhdl_parser.parse(txt)

        # remove and count ambiguities
        if self.ambig:
            from colorama import Fore

            parser2 = Lark(
                open("hdltree/vhdl-2008.lark", encoding="latin-1"),
                start="design_file",
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
            parse_tree = VhdlParseTreeTransformers.MakeAmbigUnique().transform(parse_tree)
            parse_tree = VhdlParseTreeTransformers.CollapseAmbig().transform(parse_tree)

        # convert parse tree to custom format
        # try:
        cst = self.vhdl_transformer.transform(parse_tree)
        VhdlParseTreeTransformers.AddCstParent().visit(cst)
        # except VisitError as e:
        #    print(e)
        #    print(e.__context__)
        #    errjson = e.__context__.json()
        #    print(dumps(loads(errjson), indent=2))
        return cst

    def parse_vlog(self, txt: str):
        raise NotImplementedError("Verilog parsing not yet supported!")
