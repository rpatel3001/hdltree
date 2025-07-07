import logging
from io import TextIOBase
from pathlib import Path
from lark import Lark, logger, ast_utils

from . import VhdlParseTreeTransformers
from . import VhdlCstTransformer as VhdlCst


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
            p = self.parse(txt, ftype)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            p = self.parse(txt, ftype)
        p.path = fpath
        return p

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
            p = self.parse(txt)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            p = self.parse(txt)
        p.path = fpath
        return p

    def parse(self, txt: str):
        raise NotImplementedError("Verilog parsing not yet supported!")


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
            propagate_positions=True,
        )
        self.csttransformer = ast_utils.create_transformer(
            VhdlCst, VhdlParseTreeTransformers.Tokens()
        )

    def parseFile(self, fpath: TextIOBase | Path | str):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        if isinstance(fpath, Path):
            txt = fpath.read_text("latin-1")
            p = self.parse(txt)
        elif isinstance(fpath, TextIOBase):
            txt = fpath.read()
            p = self.parse(txt)
        p.path = fpath
        return p

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
