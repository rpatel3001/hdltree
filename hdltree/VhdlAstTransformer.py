from __future__ import annotations  # for forward annotations

from typing import List, TypeAlias
from dataclasses import dataclass, field, fields
from os import getenv
from pathlib import Path
from lark import Tree as LarkTree
from sys import modules
from re import sub
from types import SimpleNamespace

import hdltree.VhdlCstTransformer as VhdlCst


if getenv("DEBUG"):
    # check datatypes with pydantic, somewhat slower
    from pydantic import ConfigDict
    from pydantic.dataclasses import dataclass

    dataclass = dataclass(slots=True, config=ConfigDict(arbitrary_types_allowed=True))
else:
    from dataclasses import dataclass
    dataclass = dataclass(slots=True)

def camel2snake(name):
    return sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()

def nonestr(val):
    return str(val) if val is not None else None

@dataclass
class Tree(LarkTree):
    # print a simple version of the CST, probably prefer rich_tree
    def print(self, level=0):
        INDENT_TOKEN = "  "

        def indent(num):
            return INDENT_TOKEN * num

        print(indent(level) + camel2snake(type(self).__name__))
        for f in fields(self):
            fobj = getattr(self, f.name)
            #if isinstance(fobj, Meta):
            #    continue
            if not isinstance(fobj, list):
                fobj = [fobj]
            else:
                level += 1
                print(indent(level) + f.name)
            for obj in fobj:
                if isinstance(obj, Tree):
                    obj.print(level + 1)
                else:
                    level += 1
                    print(indent(level) + str(obj))

    # return a rich.tree.Tree for pretty printing
    def rich_tree(self, self_meta=None):
        from rich.tree import Tree as RichTree
        from rich.markup import escape

        # expand aliases
        def deref_type(rawtype):
            newtype = []
            for rt in rawtype.split(" | "):
                try:
                    # get a reference to the containing module
                    thismodule = modules[self.__module__]  # __import__(__name__)
                    # try to get the attribute, errors out here if it doesn't exist
                    aliastype = getattr(thismodule, rt)
                    # make sure it's an alias
                    if not isinstance(aliastype, type):  # get_origin(uniontype):
                        # chop off the module name and prepend the alias name
                        nopre = sub(r"typing\.", "", str(aliastype))
                        nopre = sub(f"{__name__}\\.", "", nopre)
                        newtype.append(f"{{ {rt} = " + nopre + " }")
                    else:
                        newtype.append(rt)
                except:
                    newtype.append(rt)
            return " | ".join(newtype)

        # take the full type hint of the field and underline the actual type of the object in the field
        def annotate_type(field_type, obj):
            # remove Optional wrapper used for rules with multiple branches with different numbers of subrules/tokens and not using a Union alias
            noopt = sub(r"Optional\[(.*)\]", r"\1", field_type)
            # set search pattern
            if obj is None:
                pat = r"\b(None)\b"
            elif isinstance(obj, list):
                pat = r"(List\[.*\])"
            else:
                pat = r"\b(" + type(obj).__name__ + r")\b"
            return sub(pat, r"[underline]\1[/underline]", noopt)

        # recursively convert a CST node into a rich.tree.Tree
        def field2tree(field_meta, field_val):
            if isinstance(field_val, Tree):
                return [field_val.rich_tree(field_meta)]
            elif isinstance(field_val, list):
                annotated_type = annotate_type(deref_type(field_meta.type), field_val)
                list_branch = RichTree(
                    f"[blue] {field_meta.name}[{len(field_val)} items] [ {annotated_type} ]"
                )
                for ii, list_item in enumerate(field_val):
                    list_type = sub(r"{ .* = (.*) }", r"\1", deref_type(field_meta.type))
                    list_type = sub(r"List\[(.*)\]", r"\1", list_type)
                    list_meta = SimpleNamespace(name=f"{field_meta.name}[{ii}]", type=list_type)
                    for c in field2tree(list_meta, list_item):
                        list_branch.children.append(c)
                return [list_branch]
            elif isinstance(field_val, (str, Path, bool, VhdlCst.Identifier)) or field_val is None:
                annotated_type = annotate_type(field_meta.type, field_val)
                # token_branch = RichTree(f'{field_meta.name}{(f"[{iter}]") if iter != -1 else ""} [ {annotated_type} ]')
                token_branch = RichTree(f"{field_meta.name} [ {annotated_type} ]")
                token_branch.add(
                    f"[green]{escape(f"{field_val}") if field_val else 'None'}[/green]"
                )
                return [token_branch]
            elif field_val is None:
                return [RichTree("[green]None[/green]")]
            else:
                raise ValueError(f"unknown CST item: {escape(str(field_val))} of type {type(field_val)}")

        if self_meta is None:
            annotated_type = annotate_type(type(self).__name__, self)
            branch = RichTree(f"{camel2snake(type(self).__name__)} [ {annotated_type} ]")
        else:
            annotated_type = annotate_type(self_meta.type, self)
            branch = RichTree(self_meta.name + f" [ {annotated_type} ]")
        for field_meta in fields(self):
            field_val = getattr(self, field_meta.name)
            #if isinstance(field_val, Meta):
            #    pass
            #else:
            child = field2tree(field_meta, field_val)
            for c in child:
                branch.children.append(c)
        return branch

@dataclass
class Net(Tree):
    name: str
    access: str
    type: Type
    default: str | None

@dataclass
class InterfaceNet(Net):
    dir: str

@dataclass
class InterfaceType(Tree):
    name: str

@dataclass
class InterfaceSubprogram(Tree):
    name: str
    default: str | None

@dataclass
class InterfacePackage(Tree):
    name: str
    base_name: str

InterfaceElement: TypeAlias = InterfaceNet | InterfaceType | InterfaceSubprogram | InterfacePackage

@dataclass
class Subprogram(Tree):
    name: str

@dataclass
class Package(Tree):
    name: str
    files: List[File] = field(default_factory=list)
    has_body: bool = False
    context: Context = None
    parameters: List[InterfaceElement] = field(default_factory=list)
    components: List[Component] = field(default_factory=list)
    constants: List[Constant] = field(default_factory=list)
    types: List[Type] = field(default_factory=list)
    subprograms: List[Subprogram] = field(default_factory=list)

    def add_context(self, ctx):
        pass

    def add_package(self, pkg: VhdlCst.PackageDeclaration):
        if clause := pkg.package_header.generic_clause:
            for param in clause.interface_elements:
                p = param.generic_declaration
                if isinstance(p, VhdlCst.InterfaceConstantDeclaration):
                    for pid in p.identifier_list:
                        self.parameters.append(InterfaceNet(str(pid.id), "constant", str(p.subtype_indication), nonestr(p.default), "in"))
                elif isinstance(p, VhdlCst.InterfaceIncompleteTypeDeclaration):
                    self.parameters.append(InterfaceType(str(p.identifier)))
                elif isinstance(p, VhdlCst.InterfaceSubprogramDeclaration):
                    self.parameters.append(InterfaceSubprogram(str(p.interface_subprogram_specification), nonestr(p.interface_subprogram_default)))
                elif isinstance(p, VhdlCst.InterfacePackageDeclaration):
                    self.parameters.append(InterfacePackage(str(p.identifier), str(p.uninstantiated_package_name)))
                else:
                    raise ValueError(f"bad package generic type {type(p).__name__}")
        for dec in pkg.package_declarative_part:
            dec = dec.item
            if isinstance(dec, VhdlCst.SubprogramDeclaration):
                self.subprograms.append(Subprogram(dec.specification.specification.designator.format()))
            elif isinstance(dec, VhdlCst.SubprogramInstantiationDeclaration):
                self.subprograms.append(Subprogram(dec.identifier))


    def add_body(self, body: VhdlCst.PackageBody):
        self.has_body = True

@dataclass
class Module(Tree):
    name: str
    files: List[File] = field(default_factory=list)
    arch_name: str = ""
    context: Context = None
    parameters: List[InterfaceElement] = field(default_factory=list)
    ports: List[InterfaceNet] = field(default_factory=list)
    declarations: List[Declaration] = field(default_factory=list)
    statements: List[Statement] = field(default_factory=list)

    def add_context(self, ctx):
        pass

    def add_entity(self, ent: VhdlCst.EntityDeclaration):
        if clause := ent.entity_header.generic_clause:
            for param in clause.interface_elements:
                p = param.generic_declaration
                if isinstance(p, VhdlCst.InterfaceConstantDeclaration):
                    for pid in p.identifier_list:
                        self.parameters.append(InterfaceNet(str(pid.id), "constant", str(p.subtype_indication), nonestr(p.default), "in"))
                elif isinstance(p, VhdlCst.InterfaceIncompleteTypeDeclaration):
                    self.parameters.append(InterfaceType(str(p.identifier)))
                elif isinstance(p, VhdlCst.InterfaceSubprogramDeclaration):
                    self.parameters.append(InterfaceSubprogram(str(p.interface_subprogram_specification), nonestr(p.interface_subprogram_default)))
                elif isinstance(p, VhdlCst.InterfacePackageDeclaration):
                    self.parameters.append(InterfacePackage(str(p.identifier), str(p.uninstantiated_package_name)))
                else:
                    raise ValueError(f"bad entity generic type {type(p).__name__}")
        if clause := ent.entity_header.port_clause:
            for port in clause.interface_elements:
                p = port.port_declaration
                if isinstance(p, VhdlCst.InterfaceSignalDeclaration):
                    for pid in p.identifier_list:
                        self.ports.append(InterfaceNet(str(pid.id), "signal", str(p.subtype_indication), nonestr(p.default), str(p.mode)))
                else:
                    raise ValueError(f"bad entity port type {type(p).__name__}")

    def add_arch(self, arch: VhdlCst.ArchitectureBody):
        self.arch_name = arch.identifier

@dataclass
class File(Tree):
    path: Path

@dataclass
class Library(Tree):
    name: str
    packages: List[Package] = field(default_factory=list)
    modules:  List[Module] = field(default_factory=list)

    def get_module(self, name):
        for mod in self.modules:
            if mod.name == name:
                return mod

    def get_package(self, name):
        for pkg in self.packages:
            if pkg.name == name:
                return pkg

    def add_cst(self, cst):
        assert isinstance(cst, VhdlCst.DesignFile)
        new_mods = []
        for du in cst.design_units:
            ctx = du.context_clause
            lu = du.library_unit.unit.children[1]
            if isinstance(lu, VhdlCst.EntityDeclaration):
                name = str(lu.identifier)
                if mod := self.get_module(name):
                    raise ValueError(f"entity {name} already exists")
                print(f"creating entity {name}")
                mod = Module(name, [File(cst.path)])
                mod.add_context(ctx)
                mod.add_entity(lu)
                self.modules.append(mod)
                new_mods.append(mod)
            elif isinstance(lu, VhdlCst.ArchitectureBody):
                name = str(lu.identifier)
                if mod := self.get_module(name):
                    if mod.identifier:
                        raise ValueError(f"entity {name} already has an architecture ({mod.identifier})")
                    mod.add_context(ctx)
                    mod.add_arch(lu)
                else:
                    raise ValueError(f"entity {name} doesn't exist")
            elif isinstance(lu, VhdlCst.PackageDeclaration):
                name = str(lu.identifier)
                if pkg := self.get_package(name):
                    raise ValueError(f"package {name} already exists")
                print(f"creating package {name}")
                pkg = Package(name, [File(cst.path)])
                pkg.add_context(ctx)
                pkg.add_package(lu)
                self.packages.append(pkg)
                new_mods.append(pkg)
            elif isinstance(lu, VhdlCst.PackageBody):
                name = str(lu.simple_name)
                if pkg := self.get_package(name):
                    if pkg.has_body:
                        raise ValueError(f"package {name} already has a body")
                    pkg.add_context(ctx)
                    pkg.add_body(lu)
                else:
                    raise ValueError(f"package {name} doesn't exist")
            else:
                print(f"unsupported {type(lu).__name__}")
        return new_mods

@dataclass
class Project(Tree):
    libraries: List[Library] = field(default_factory=list)

    def get_library(self, name: str) -> Library:
        for lib in self.libraries:
            if lib.name == name:
                return lib
        self.libraries.append(Library(name))
        return self.libraries[-1]
