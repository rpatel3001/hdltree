from sys import stdout, stderr
import logging
from pathlib import Path
from json import dumps, loads
from lark import Lark, logger, ast_utils
from lark_ambig_tools import CountTrees
from lark.exceptions import VisitError
from rich import print as richprint

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


def filetype(fpath: Path):
    fileext = fpath.suffix[1:]
    if fileext in ["vhd", "vhdl", "vho", "vht"]:
        return "VHDL"
    elif fileext in ["v", "vh", "verilog", "vlg", "vo", "vqm", "vt", "veo", "sv", "svh", "vlog"]:
        return "VLOG"
    else:
        return fileext.upper()


class HdlParser:
    def __init__(self, use_regex=True, debug=False):
        if debug:
            logger.setLevel(logging.DEBUG)
        self.vhdl_parser = VhdlParser(use_regex, debug)
        self.vlog_parser = VerilogParser(use_regex, debug)

    def parseFile(self, fpath: Path | str, ftype: str = ""):
        if isinstance(fpath, str):
            fpath = Path(fpath)
        ftype = ftype.upper()
        if ftype not in ["VHDL", "VLOG"]:
            ftype = filetype(fpath)

        txt = fpath.read_text("latin-1")
        return self.parse(txt, ftype)

    def parse(self, txt: str, ftype: str = "VHDL"):
        if ftype == "VHDL":
            return self.vhdl_parser.parse(txt)
        elif ftype == "VLOG":
            return self.vlog_parser.parse(txt)
        else:
            raise ValueError(f"unknown file type {ftype}")


class VerilogParser:
    def __init__(self, use_regex=True, debug=False):
        pass

    def parseFile(self, fpath: Path | str, ftype: str = ""):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        txt = fpath.read_text("latin-1")
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
    def __init__(self, use_regex=True, debug=False):
        try:
            import regex

            use_regex = True
        except ModuleNotFoundError:
            use_regex = False

        self.parser = Lark(
            open(Path(__file__).parent / "vhdl-2008.lark", encoding="latin-1"),
            start="design_file",
            regex=use_regex,
            debug=debug,
            ambiguity="explicit",
            lexer="dynamic",
        )
        self.csttransformer = ast_utils.create_transformer(
            VhdlCstTransformer, VhdlParseTreeTransformers.Tokens()
        )

    def parseFile(self, fpath: Path | str, ftype: str = ""):
        if isinstance(fpath, str):
            fpath = Path(fpath)

        txt = fpath.read_text("latin-1")
        return self.parse(txt)

    def parse(self, txt: str):
        # parse code to tree
        parse_tree = self.parser.parse(txt)

        # remove and count ambiguities
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


def main():
    ve = VhdlParser()
    code = '''
package foo is
  function afunc(q,w,e : std_ulogic; h,j,k : unsigned) return std_ulogic;

  procedure aproc( r,t,y : in std_ulogic; u,i,o : out signed);

  component acomp is
    port (
      a,b,c : in std_ulogic;    -- no default value
      f,g,h : inout bit := '1'; -- bit ports
      v : in std_logic_vector(lBound -1 downto 0) -- array range
    ); -- port list comment

  end component;

end package;
  '''

    cst = ve.parse(code)
    richprint(cst.rich_tree())


if __name__ == '__main__':
    main()
