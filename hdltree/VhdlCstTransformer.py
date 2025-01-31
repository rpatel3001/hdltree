from __future__ import annotations  # for forward annotations

from sys import modules
from os import getenv
from types import SimpleNamespace
from typing import List, Optional
from lark import ast_utils, Token, Tree
from lark.tree import Meta
from dataclasses import InitVar, fields
from re import sub

if getenv("DEBUG"):
    # check datatypes with pydantic, somewhat slower
    from pydantic import ConfigDict
    from pydantic.dataclasses import dataclass

    dataclass = dataclass(config=ConfigDict(arbitrary_types_allowed=True))
else:
    from dataclasses import dataclass

nl = "\n"


# return a string representation of an object
# join with `sep` if it's an array
# prepend `pre` and postpend `post` iff the object resolves to a nonempty string
def nonestr(val, pre="", post="", sep=""):
    if isinstance(val, list):
        assert sep != ""
        valstr = sep.join(map(str, val))
    else:
        valstr = str(val)
    if val is not None and valstr != "":
        return str(pre) + valstr + str(post)
    else:
        return ""


def camel2snake(name):
    return sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()


# Base class for CST nodes to get picked up by lark
# This will be skipped by create_transformer(), because it starts with an underscore
@dataclass
class _VhdlCstNode(Tree, ast_utils.Ast):  # , ast_utils.WithMeta):
    # meta: Meta

    def __str__(self):
        return self.format()

    def add_parent(self, parent):
        super().__setattr__("parent", parent)

    @property
    def data(self):
        return type(self).__name__

    @property
    def meta(self):
        return None

    @property
    def children(self):
        fs = fields(self)
        fv0 = getattr(self, fs[0].name)
        if len(fs) == 1 and isinstance(fv0, list):
            return fv0
        else:
            children = []
            for field_meta in fields(self):
                field_val = getattr(self, field_meta.name)
                if isinstance(field_val, list):
                    children += field_val
                else:
                    children.append(field_val)
                # if not isinstance(field_val, list) and field_val is not None:
                #  children.append(field_val)
                # elif field_val is not None:
                #  children.append(Tree("list", field_val))
            return children

    @property
    def libraries(self):
        libraries = []
        for c in self.find_data("LibraryClause"):
            libraries += [str(l) for l in c.logical_names]
        return libraries

    @property
    def packages(self):
        packages = []
        for c in self.find_data("UseClause"):
            packages += [str(l) for l in c.selected_names]
        return packages

    @property
    def entities(self):
        return self.find_data("EntityDeclaration")

    @property
    def generics(self):
        clause = list(self.find_data("GenericClause"))
        if clause:
            return clause[0].interface_elements
        else:
            return []

    @property
    def ports(self):
        clause = list(self.find_data("PortClause"))
        if clause:
            return clause[0].interface_elements
        else:
            return []

    # print a simple version of the CST, probably prefer rich_tree
    def print(self, level=0):
        INDENT_TOKEN = "  "

        def indent(num):
            return INDENT_TOKEN * num

        print(indent(level) + camel2snake(type(self).__name__))
        for f in fields(self):
            fobj = getattr(self, f.name)
            if isinstance(fobj, Meta):
                continue
            if not isinstance(fobj, list):
                fobj = [fobj]
            else:
                level += 1
                print(indent(level) + f.name)
            for obj in fobj:
                if isinstance(obj, _VhdlCstNode):
                    obj.print(level + 1)
                else:
                    level += 1
                    print(indent(level) + str(obj))

    # return a rich.tree.Tree for pretty printing
    def rich_tree(self, self_meta=None):
        from rich.tree import Tree as RichTree

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
            if isinstance(field_val, _VhdlCstNode):
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
            elif isinstance(field_val, Token) or field_val is None:
                annotated_type = annotate_type(field_meta.type, field_val)
                # token_branch = RichTree(f'{field_meta.name}{(f"[{iter}]") if iter != -1 else ""} [ {annotated_type} ]')
                token_branch = RichTree(f"{field_meta.name} [ {annotated_type} ]")
                token_branch.add(
                    f"[green]{field_val}[/green]"
                    + (f" line {field_val.line} char {field_val.column}" if field_val else "")
                )
                return [token_branch]
            elif field_val is None:
                return [RichTree("[green]None[/green]")]
            else:
                raise ValueError(f"unknown CST item: {field_val}\n\nin Tree {field_val.parent}")

        if self_meta is None:
            annotated_type = annotate_type(type(self).__name__, self)
            branch = RichTree(f"{camel2snake(type(self).__name__)} [ {annotated_type} ]")
        else:
            annotated_type = annotate_type(self_meta.type, self)
            branch = RichTree(self_meta.name + f" [ {annotated_type} ]")
        for field_meta in fields(self):
            field_val = getattr(self, field_meta.name)
            if isinstance(field_val, Meta):
                pass
            else:
                child = field2tree(field_meta, field_val)
                for c in child:
                    branch.children.append(c)
        return branch


# subclass of _VhdlCstNode that takes a single argument that's a list of subTrees/Tokens
@dataclass
class _VhdlCstListNode(_VhdlCstNode, ast_utils.AsList):
    pass


@dataclass
class ExtendedIdentifier(_VhdlCstNode):
    id: Token

    def format(self):
        return self.id


@dataclass
class Identifier(_VhdlCstNode):
    id: Token | ExtendedIdentifier

    def format(self):
        return str(self.id)


@dataclass
class CharacterLiteral(_VhdlCstNode):
    char: Token

    def format(self):
        return "'" + str(self.char) + "'"


@dataclass
class BitStringLiteral(_VhdlCstNode):
    width: Token | None
    base_spec: Token
    bit_value: Token

    def format(self):
        return nonestr(self.width) + self.base_spec + '"' + self.bit_value + '"'


@dataclass
class Exponent(_VhdlCstNode):
    sign: Token | None
    exponent: Token

    def format(self):
        return "E" + nonestr(self.sign) + str(self.exponent)


@dataclass
class DecimalLiteral(_VhdlCstNode):
    integer: Token
    decimal: Token | None
    exponent: Exponent | None

    def format(self):
        return str(self.integer) + nonestr(self.decimal, pre=".") + nonestr(self.exponent)


@dataclass
class BasedLiteral(_VhdlCstNode):
    base: Token
    integer: Token
    decimal: Token | None
    exponent: Exponent | None

    def format(self):
        return (
            str(self.base)
            + "#"
            + str(self.integer)
            + nonestr(self.decimal, pre=".")
            + "#"
            + nonestr(self.exponent)
        )


@dataclass
class AbstractLiteral(_VhdlCstNode):
    abstract_literal: DecimalLiteral | BasedLiteral

    def format(self):
        return str(self.abstract_literal)


@dataclass
class PhysicalLiteral(_VhdlCstNode):
    abstract_literal: AbstractLiteral | None
    unit_name: Identifier

    def format(self):
        return f"{nonestr(self.abstract_literal, post=' ')}{self.unit_name}"


@dataclass
class NumericLiteral(_VhdlCstNode):
    numeric_literal: AbstractLiteral | PhysicalLiteral

    def format(self):
        return str(self.numeric_literal)


@dataclass
class StringLiteral(_VhdlCstNode):
    string: Token | None

    def format(self):
        return '"' + nonestr(self.string) + '"'


@dataclass
class Literal(_VhdlCstNode):
    item: NumericLiteral | StringLiteral | BitStringLiteral

    def format(self):
        return str(self.item)


@dataclass
class FunctionCall(_VhdlCstNode):
    name: Name
    parameters: List[AssociationElement] | None

    def format(self):
        return str(self.name) + nonestr(self.parameters, pre="(", post=")", sep=", ")


@dataclass
class QualifiedExpression(_VhdlCstNode):
    type_mark: TypeMark
    expression: Expression | Aggregate

    def format(self):
        if isinstance(self.expression, Expression):
            return f"{self.type_mark}'({self.expression})"
        else:
            return f"{self.type_mark}'{self.expression}"


@dataclass
class Allocator(_VhdlCstNode):
    allocator: SubtypeIndication | QualifiedExpression

    def format(self):
        return f"new {self.allocator}"


@dataclass
class Primary(_VhdlCstNode):
    item: Name | Literal | Aggregate | FunctionCall | QualifiedExpression | Allocator | Expression

    def format(self):
        if isinstance(self.item, Expression):
            return "(" + str(self.item) + ")"
        else:
            return str(self.item)


@dataclass
class Factor(_VhdlCstListNode):
    _list: InitVar[tuple[Token, Primary] | tuple[Primary, Primary | None]]
    factor_op: Optional[Token | None] = None
    primary: Optional[Primary] = None
    exponent: Optional[Token | None] = None

    def __post_init__(self, _list):
        if isinstance(_list[0], Token):
            super().__setattr__("factor_op", _list[0])
            super().__setattr__("primary", _list[1])
            super().__setattr__("exponent", None)
        else:
            super().__setattr__("factor_op", None)
            super().__setattr__("primary", _list[0])
            super().__setattr__("exponent", _list[1])

    def format(self):
        if self.factor_op:
            return f"{self.factor_op} {self.primary}"
        else:
            return f"{self.primary}{nonestr(self.exponent, pre='**')}"


@dataclass
class TermOp(_VhdlCstNode):
    op: Token
    factor: Factor

    def format(self):
        return f"{self.op} {self.factor}"


@dataclass
class Term(_VhdlCstNode):
    factor: Factor
    ops: List[TermOp]

    def format(self):
        return str(self.factor) + nonestr(self.ops, sep=" ", pre=" ")


@dataclass
class SimpleExpressionOp(_VhdlCstNode):
    op: Token
    term: Term

    def format(self):
        return f"{self.op} {self.term}"


@dataclass
class SimpleExpression(_VhdlCstNode):
    sign: Token | None
    term: Term
    ops: List[SimpleExpressionOp]

    def format(self):
        return nonestr(self.sign) + f"{self.term}" + nonestr(self.ops, sep=" ", pre=" ")


@dataclass
class ShiftExpression(_VhdlCstNode):
    expr1: SimpleExpression
    shift_op: Token | None
    expr2: SimpleExpression | None

    def format(self):
        return str(self.expr1) + nonestr(self.shift_op, pre=" ") + nonestr(self.expr2, pre=" ")


@dataclass
class Relation(_VhdlCstNode):
    expr1: ShiftExpression
    rel_op: Token | None
    expr2: ShiftExpression | None

    def format(self):
        return str(self.expr1) + nonestr(self.rel_op, pre=" ") + nonestr(self.expr2, pre=" ")


@dataclass
class LogicalExpression(_VhdlCstListNode):
    logical_tokens: List[Relation | Token]

    def format(self):
        return nonestr(self.logical_tokens, sep=" ")


@dataclass
class Expression(_VhdlCstListNode):
    _list: InitVar[tuple[Token, Primary] | tuple[LogicalExpression]]
    conditional: Optional[Token | None] = None
    expression: Optional[LogicalExpression] = None

    def __post_init__(self, _list):
        terms = len(_list)
        if 2 == terms:
            super().__setattr__("conditional", _list[0])
            super().__setattr__("expression", _list[1])
        elif 1 == terms:
            super().__setattr__("conditional", None)
            super().__setattr__("expression", _list[0])

    def format(self):
        return nonestr(self.conditional, post=" ") + str(self.expression)


@dataclass
class RangeLiteral(_VhdlCstNode):
    left: SimpleExpression
    direction: Token
    right: SimpleExpression

    def format(self):
        return f"{self.left} {self.direction} {self.right}"


@dataclass
class DiscreteRange(_VhdlCstNode):
    range: SubtypeIndication | Range

    def format(self):
        return str(self.range)


@dataclass
class IndexConstraint(_VhdlCstListNode):
    discrete_ranges: List[DiscreteRange]

    def format(self):
        return "(" + nonestr(self.discrete_ranges, sep=", ") + ")"


@dataclass
class RecordElementConstraint(_VhdlCstNode):
    record_element_simple_name: Identifier
    constraint: ArrayConstraint | RecordConstraint

    def format(self):
        return f"{self.record_element_simple_name} {self.constraint}"


@dataclass
class RecordConstraint(_VhdlCstListNode):
    record_element_constraints: List[RecordElementConstraint]

    def format(self):
        return "(" + nonestr(self.record_element_constraints, sep=", ") + ")"


@dataclass
class ArrayElementConstraint(_VhdlCstNode):
    element_constraint: ArrayConstraint | RecordConstraint

    def format(self):
        return str(self.element_constraint)


@dataclass
class ArrayConstraint(_VhdlCstNode):
    index_constraint: IndexConstraint | Token
    array_element_constraint: ArrayElementConstraint | None

    def format(self):
        return str(self.index_constraint) + nonestr(self.array_element_constraint)


@dataclass
class RangeConstraint(_VhdlCstNode):
    range: Range

    def format(self):
        return f" range {self.range}"


@dataclass
class Constraint(_VhdlCstNode):
    constraint: RangeConstraint | ArrayConstraint | RecordConstraint

    def format(self):
        return str(self.constraint)


@dataclass
class Choice(_VhdlCstNode):
    choice: SimpleExpression | DiscreteRange | Identifier | Token

    def format(self):
        return str(self.choice)


@dataclass
class Choices(_VhdlCstListNode):
    choices: List[Choice]

    def format(self):
        return nonestr(self.choices, sep=" | ")


@dataclass
class ElementAssociation(_VhdlCstNode):
    choices: Choices | None
    expression: Expression

    def format(self):
        return nonestr(self.choices, post=" => ") + str(self.expression)


@dataclass
class Aggregate(_VhdlCstListNode):
    element_associations: List[ElementAssociation]

    def format(self):
        return "(" + nonestr(self.element_associations, sep=", ") + ")"


@dataclass
class IndexedName(_VhdlCstNode):
    prefix: Prefix
    expressions: List[Expression]

    def format(self):
        return f"{self.prefix}({nonestr(self.expressions, sep=', ')})"


@dataclass
class AttributeName(_VhdlCstNode):
    prefix: Prefix
    signature: Signature | None
    attribute_designator: Identifier
    expression: Expression | None

    def format(self):
        return f"{self.prefix}{nonestr(self.signature)}'{self.attribute_designator}{nonestr(self.expression, pre='(', post=')')}"


Range = AttributeName | RangeLiteral


@dataclass
class SliceName(_VhdlCstNode):
    prefix: Prefix
    discrete_range: DiscreteRange

    def format(self):
        return f"{self.prefix}({self.discrete_range})"


@dataclass
class Name(_VhdlCstNode):
    name_val: (
        Identifier
        | Token
        | CharacterLiteral
        | SelectedName
        | IndexedName
        | SliceName
        | AttributeName
    )

    def format(self):
        return f"{self.name_val}"


@dataclass
class Prefix(_VhdlCstNode):
    name: Name

    def format(self):
        return f"{self.name}"


@dataclass
class Suffix(_VhdlCstNode):
    name: Identifier | Token

    def format(self):
        return f"{self.name}"


@dataclass
class SelectedName(_VhdlCstNode):
    prefix: Prefix
    suffix: Suffix

    def format(self):
        return f"{self.prefix}.{self.suffix}"


@dataclass
class TypeMark(_VhdlCstNode):
    name: Name

    def format(self):
        return str(self.name)


@dataclass
class RecordElementResolution(_VhdlCstNode):
    record_element_simple_name: Identifier
    resolution_indication: ResolutionIndication

    def format(self):
        return str(self.name)


@dataclass
class RecordResolution(_VhdlCstNode):
    items: List[RecordElementResolution]

    def format(self):
        return nonestr(self.items, sep=", ")


@dataclass
class ElementResolution(_VhdlCstNode):
    item: ResolutionIndication | RecordResolution

    def format(self):
        return str(self.item)


@dataclass
class ResolutionIndication(_VhdlCstNode):
    item: Name | ElementResolution

    def format(self):
        if isinstance(self.item, Name):
            return str(self.item)
        else:
            return f"({str(self.item)})"


@dataclass
class SubtypeIndication(_VhdlCstNode):
    resolution_indication: ResolutionIndication | None
    type_mark: TypeMark
    constraint: Constraint | None

    def format(self):
        return f"{nonestr(self.resolution_indication, post=' ')}{self.type_mark}{(nonestr(self.constraint))}"


@dataclass
class InterfaceSignalDeclaration(_VhdlCstNode):
    SIGNAL: Token | None
    identifier_list: List[Identifier]
    mode: Token | None
    subtype_indication: SubtypeIndication
    bus: Token | None
    default: Expression | None

    def format(self):
        return (
            nonestr(self.SIGNAL, post=" ")
            + nonestr(self.identifier_list, sep=", ")
            + " : "
            + nonestr(self.mode, post=" ")
            + str(self.subtype_indication)
            + nonestr(self.default, pre=" := ")
        )


@dataclass
class InterfaceVariableDeclaration(_VhdlCstNode):
    VARIABLE: Token | None
    identifier_list: List[Identifier]
    mode: Token | None
    subtype_indication: SubtypeIndication
    default: Expression | None

    def format(self):
        return (
            nonestr(self.VARIABLE, post=" ")
            + nonestr(self.identifier_list, sep=", ")
            + " : "
            + nonestr(self.mode, post=" ")
            + str(self.subtype_indication)
            + nonestr(self.default, pre=" := ")
        )


@dataclass
class InterfaceConstantDeclaration(_VhdlCstNode):
    CONSTANT: Token | None
    identifier_list: List[Identifier]
    mode: Token | None
    subtype_indication: SubtypeIndication
    default: Expression | None

    def format(self):
        return (
            nonestr(self.CONSTANT, post=" ")
            + nonestr(self.identifier_list, sep=", ")
            + " : "
            + nonestr(self.mode, post=" ")
            + str(self.subtype_indication)
            + nonestr(self.default, pre=" := ")
        )


@dataclass
class InterfaceIncompleteTypeDeclaration(_VhdlCstNode):
    identifier: Identifier

    def format(self):
        return f"type {self.identifier}"


@dataclass
class InterfacePackageGenericMapAspect(_VhdlCstNode):
    aspect: GenericMapAspect | Token

    def format(self):
        if isinstance(self.aspect, Token):
            return f"generic map ({self.aspect})"
        else:
            return f"{self.aspect}"


@dataclass
class InterfacePackageDeclaration(_VhdlCstNode):
    identifier: Identifier
    uninstantiated_package_name: Name
    interface_package_generic_map_aspect: InterfacePackageGenericMapAspect

    def format(self):
        return f"package {self.identifier} is new {self.uninstantiated_package_name} {self.interface_package_generic_map_aspect}"


@dataclass
class InterfaceProcedureSpecification(_VhdlCstNode):
    designator: Designator
    PARAMETER: Token | None
    formal_parameter_list: List[ParameterInterfaceElement] | None

    def format(self):
        return (
            f"procedure {self.designator}\n"
            + nonestr(self.PARAMETER, post=" ")
            + nonestr(self.formal_parameter_list, pre="(", sep=";\n", post="\n)")
        )


@dataclass
class InterfaceFunctionSpecification(_VhdlCstNode):
    pure: Token | None
    designator: Designator
    PARAMETER: Token | None
    formal_parameter_list: List[ParameterInterfaceElement] | None
    type_mark: TypeMark

    def format(self):
        return (
            f"{nonestr(self.pure, post=' ')}function {self.designator}"
            + nonestr(self.PARAMETER, pre=" ")
            + nonestr(self.formal_parameter_list, pre=" (", sep=";\n", post="\n)")
            + f" return {self.type_mark}"
        )


@dataclass
class InterfaceSubprogramSpecification(_VhdlCstNode):
    aspect: InterfaceProcedureSpecification | InterfaceFunctionSpecification

    def format(self):
        return f"{self.aspect}"


@dataclass
class InterfaceSubprogramDefault(_VhdlCstNode):
    name: Name | Token

    def format(self):
        return f"{self.name}"


@dataclass
class InterfaceSubprogramDeclaration(_VhdlCstNode):
    interface_subprogram_specification: InterfaceSubprogramSpecification
    interface_subprogram_default: InterfaceSubprogramDefault | None

    def format(self):
        return f"{self.interface_subprogram_specification}{nonestr(self.interface_subprogram_default, pre=' is ')}"


@dataclass
class GenericInterfaceElement(_VhdlCstNode):
    generic_declaration: (
        InterfaceConstantDeclaration
        | InterfaceIncompleteTypeDeclaration
        | InterfaceSubprogramDeclaration
        | InterfacePackageDeclaration
    )

    def format(self):
        return str(self.generic_declaration)


@dataclass
class InterfaceFileDeclaration(_VhdlCstNode):
    identifier_list: List[Identifier]
    subtype_indication: SubtypeIndication

    def format(self):
        return (
            f"file {nonestr(self.identifier_list, sep=', ')}" + " : " + str(self.subtype_indication)
        )


@dataclass
class FileOpenInformation(_VhdlCstNode):
    open_kind: Expression | None
    name: Expression

    def format(self):
        return nonestr(self.open_kind, pre=f"open ") + f"is {self.name}"


@dataclass
class FileDeclaration(_VhdlCstNode):
    identifier_list: List[Identifier]
    subtype_indication: SubtypeIndication
    open_info: FileOpenInformation | None

    def format(self):
        return (
            f"file {nonestr(self.identifier_list, sep=', ')}"
            + " : "
            + str(self.subtype_indication)
            + nonestr(self.open_info, pre=" ")
            + ";"
        )


@dataclass
class ParameterInterfaceElement(_VhdlCstNode):
    parameter_declaration: (
        InterfaceConstantDeclaration
        | InterfaceSignalDeclaration
        | InterfaceVariableDeclaration
        | InterfaceFileDeclaration
    )

    def format(self):
        return str(self.parameter_declaration)


@dataclass
class PortInterfaceElement(_VhdlCstNode):
    port_declaration: InterfaceSignalDeclaration

    def format(self):
        return str(self.port_declaration)


@dataclass
class GenericClause(_VhdlCstListNode):
    interface_elements: List[GenericInterfaceElement]

    def format(self):
        return f"generic (\n" + nonestr(self.interface_elements, sep=f";\n") + f"\n);"


@dataclass
class PortClause(_VhdlCstListNode):
    interface_elements: List[PortInterfaceElement]

    def format(self):
        return f"port (\n" + nonestr(self.interface_elements, sep=f";\n") + f"\n);"


@dataclass
class EntityDeclarativeItem(_VhdlCstNode):
    item: (
        SubprogramDeclaration
        | SubprogramBody
        | SubprogramInstantiationDeclaration
        | PackageDeclaration
        | PackageBody
        | PackageInstantiationDeclaration
        | TypeDeclaration
        | SubtypeDeclaration
        | ConstantDeclaration
        | SignalDeclaration
        | FileDeclaration
        | AliasDeclaration
        | AttributeDeclaration
        | AttributeSpecification
        | UseClause
    )

    def format(self):
        return f"{self.item}"


@dataclass
class EntityStatement(_VhdlCstNode):
    item: Token

    def format(self):
        return f"{self.item}"


@dataclass
class EntityStatementPart(_VhdlCstListNode):
    items: List[EntityStatement]

    def format(self):
        return nonestr(self.items, sep=f"\n")


@dataclass
class EntityHeader(_VhdlCstNode):
    generic_clause: GenericClause | None
    port_clause: PortClause | None

    def format(self):
        return nonestr(self.generic_clause, post="\n" if self.port_clause else "") + nonestr(
            self.port_clause
        )


@dataclass
class EntityDeclaration(_VhdlCstNode):
    identifier: Identifier
    entity_header: EntityHeader
    entity_declarative_part: List[EntityDeclarativeItem] | None
    entity_statement_part: EntityStatementPart | None
    ENTITY: Token | None
    element_simple_name: Identifier | None

    def format(self):
        return (
            f"entity {self.identifier} is\n{self.entity_header}\n"
            + nonestr(self.entity_declarative_part, sep="\n", post="\n")
            + nonestr(self.entity_statement_part, pre="begin\n", post="\n")
            + "end"
            + nonestr(self.ENTITY, pre=" ")
            + nonestr(self.element_simple_name, pre=" ")
            + ";\n"
        )


@dataclass
class ComponentDeclaration(_VhdlCstNode):
    identifier: Identifier
    IS: Token | None
    local_generic_clause: GenericClause | None
    local_port_clause: PortClause | None
    component_simple_name: Identifier | None

    def format(self):
        return (
            f"component {self.identifier}{nonestr(self.IS, pre=' ')}\n"
            + nonestr(self.local_generic_clause, post="\n")
            + nonestr(self.local_port_clause, post="\n")
            + "end component"
            + nonestr(self.component_simple_name, pre=" ")
            + ";\n"
        )


@dataclass
class LogicalName(_VhdlCstNode):
    identifier: Identifier

    def format(self):
        return str(self.identifier)


@dataclass
class LibraryClause(_VhdlCstListNode):
    logical_names: List[LogicalName]

    def format(self):
        return "library " + nonestr(self.logical_names, sep=f", ") + ";"


@dataclass
class UseClause(_VhdlCstListNode):
    selected_names: List[SelectedName]

    def format(self):
        return "use " + nonestr(self.selected_names, sep=f", ") + ";"


@dataclass
class ContextItem(_VhdlCstNode):
    clause: LibraryClause | UseClause | List[SelectedName]

    def format(self):
        if isinstance(self.clause, list):
            return nonestr(self.clause, pre="context ", sep=", ", post=";")
        else:
            return str(self.clause)


@dataclass
class ContextClause(_VhdlCstListNode):
    context_items: List[ContextItem]

    def format(self):
        return nonestr(self.context_items, post="\n", sep="\n")


@dataclass
class FormalPart(_VhdlCstListNode):
    _list: InitVar[tuple[Name] | tuple[Identifier | TypeMark, Name]]
    formal: Optional[Name] = None
    function_name: Optional[Identifier] = None
    type: Optional[TypeMark] = None

    def __post_init__(self, _list):
        if isinstance(_list[0], Name):
            super().__setattr__("formal", _list[0])
        elif isinstance(_list[0], Identifier):
            super().__setattr__("function_name", _list[0])
            super().__setattr__("formal", _list[1])
        else:
            super().__setattr__("type", _list[0])
            super().__setattr__("formal", _list[1])

    def format(self):
        if self.function_name:
            return f"{self.function_name}({self.formal})"
        elif self.type:
            return f"{self.type}({self.formal})"
        else:
            return f"{self.formal}"


@dataclass
class ActualDesignator(_VhdlCstListNode):
    _list: InitVar[tuple[Token | None, Expression] | tuple[Name | SubtypeIndication | Token]]
    INERTIAL: Optional[Token | None] = None
    actual: Optional[Expression | Name | SubtypeIndication | Token] = None

    def __post_init__(self, _list):
        if 2 == len(_list):
            super().__setattr__("INERTIAL", _list[0])
            super().__setattr__("actual", _list[1])
        elif isinstance(_list[0], Identifier):
            super().__setattr__("actual", _list[0])
        else:
            super().__setattr__("actual", _list[0])

    def format(self):
        return nonestr(self.INERTIAL, post=" ") + str(self.actual)


@dataclass
class ActualPart(_VhdlCstListNode):
    _list: InitVar[tuple[ActualDesignator] | tuple[Identifier | TypeMark, ActualDesignator]]
    actual: Optional[ActualDesignator] = None
    function_name: Optional[Identifier] = None
    type: Optional[TypeMark] = None

    def __post_init__(self, _list):
        if isinstance(_list[0], ActualDesignator):
            super().__setattr__("actual", _list[0])
        elif isinstance(_list[0], Identifier):
            super().__setattr__("function_name", _list[0])
            super().__setattr__("actual", _list[1])
        else:
            super().__setattr__("type", _list[0])
            super().__setattr__("actual", _list[1])

    def format(self):
        if self.function_name:
            return f"{self.function_name}({self.actual})"
        elif self.type:
            return f"{self.type}({self.actual})"
        else:
            return f"{self.actual}"


@dataclass
class AssociationElement(_VhdlCstNode):
    formal: FormalPart | None
    actual: ActualPart

    def format(self):
        return nonestr(self.formal, post=" => ") + str(self.actual)


@dataclass
class GenericMapAspect(_VhdlCstNode):
    association_list: List[AssociationElement]

    def format(self):
        return f"generic map (\n" + nonestr(self.association_list, sep=",\n", post="\n") + ")"


@dataclass
class PortMapAspect(_VhdlCstNode):
    association_list: List[AssociationElement]

    def format(self):
        return f"port map (\n" + nonestr(self.association_list, sep=",\n", post="\n") + ")"


@dataclass
class PackageHeader(_VhdlCstNode):
    generic_clause: GenericClause | None
    generic_map_aspect: GenericMapAspect | None

    def format(self):
        return nonestr(self.generic_clause, post="\n") + nonestr(
            self.generic_map_aspect, post=";\n"
        )


@dataclass
class IndexSubtypeDefinition(_VhdlCstNode):
    type_mark: TypeMark

    def format(self):
        return f"{self.type_mark} range <>"


@dataclass
class UnboundedArrayDefinition(_VhdlCstNode):
    definition: List[IndexSubtypeDefinition]
    subtype_indication: SubtypeIndication

    def format(self):
        return f"array ({nonestr(self.definition, sep=', ')}) of {self.subtype_indication}"


@dataclass
class ConstrainedArrayDefinition(_VhdlCstNode):
    index_constraint: IndexConstraint
    subtype_indication: SubtypeIndication

    def format(self):
        return f"array{nonestr(self.index_constraint)} of {self.subtype_indication}"


@dataclass
class ArrayTypeDefinition(_VhdlCstNode):
    definition: UnboundedArrayDefinition | ConstrainedArrayDefinition

    def format(self):
        return str(self.definition)


@dataclass
class ElementDeclaration(_VhdlCstNode):
    identifiers: List[Identifier]
    subtype_indication: SubtypeIndication

    def format(self):
        return f"{nonestr(self.identifiers, sep=', ')}: {self.subtype_indication};"


@dataclass
class RecordTypeDefinition(_VhdlCstNode):
    declarations: List[ElementDeclaration]
    record_type_simple_name: Identifier | None

    def format(self):
        return f"record\n{nonestr(self.declarations, sep=nl)}\nend record{nonestr(self.record_type_simple_name, pre=' ')}"


@dataclass
class CompositeTypeDefinition(_VhdlCstNode):
    definition: ArrayTypeDefinition | RecordTypeDefinition

    def format(self):
        return str(self.definition)


@dataclass
class EnumerationLiteral(_VhdlCstNode):
    literal: Identifier | CharacterLiteral

    def format(self):
        return str(self.literal)


@dataclass
class EnumerationTypeDefinition(_VhdlCstListNode):
    literals: List[EnumerationLiteral]

    def format(self):
        return nonestr(self.literals, sep=", ", pre="(", post=")")


@dataclass
class ScalarTypeDefinition(_VhdlCstNode):
    definition: EnumerationTypeDefinition

    def format(self):
        return str(self.definition)


@dataclass
class AccessTypeDefinition(_VhdlCstNode):
    subtype_indication: SubtypeIndication

    def format(self):
        return f"access {self.subtype_indication}"


@dataclass
class FileTypeDefinition(_VhdlCstNode):
    type_mark: TypeMark

    def format(self):
        return f"file of {self.type_mark}"


@dataclass
class EntityTag(_VhdlCstNode):
    tag: Identifier | CharacterLiteral | Token

    def format(self):
        return f"{self.tag}"


@dataclass
class EntityDesignator(_VhdlCstNode):
    entity_tag: EntityTag
    signature: Signature | None

    def format(self):
        return f"{self.entity_tag}" + nonestr(self.signature)


@dataclass
class EntityClass(_VhdlCstNode):
    entity_class: Token

    def format(self):
        return f"{self.entity_class}"


@dataclass
class EntitySpecification(_VhdlCstNode):
    entity_name_list: List[EntityDesignator] | Token
    entity_class: EntityClass

    def format(self):
        return f"{nonestr(self.entity_name_list, sep=', ')} : {self.entity_class}"


@dataclass
class AttributeSpecification(_VhdlCstNode):
    designator: Identifier
    specification: EntitySpecification
    expression: Expression

    def format(self):
        return f"attribute {self.designator} of {self.specification} is {self.expression};"


@dataclass
class SubprogramInstantiationDeclaration(_VhdlCstNode):
    kind: Token
    identifier: Identifier
    name: Name
    signature: Signature | None
    generic_map_aspect: GenericMapAspect | None

    def format(self):
        return f"{self.kind} {self.identifier} is new {self.name}{nonestr(self.signature)}{nonestr(self.generic_map_aspect, pre=' ')};"


@dataclass
class ProtectedTypeDeclarativeItem(_VhdlCstNode):
    item: (
        SubprogramDeclaration
        | SubprogramInstantiationDeclaration
        | AttributeSpecification
        | UseClause
    )

    def format(self):
        return str(self.item)


@dataclass
class ProtectedTypeDeclaration(_VhdlCstNode):
    declarative_part: List[ProtectedTypeDeclarativeItem]
    simple_name: Identifier | None

    def format(self):
        return (
            f"protected\n{nonestr(self.declarative_part, sep=nl, post=nl)} end protected"
            + nonestr(self.simple_name, pre=" ")
        )


@dataclass
class ProtectedTypeBody(_VhdlCstNode):
    declarative_part: List[ProtectedTypeBodyDeclarativeItem]
    simple_name: Identifier | None

    def format(self):
        return (
            f"protected body\n{nonestr(self.declarative_part, sep=nl, post=nl)}end protected body"
            + nonestr(self.simple_name, pre=" ")
        )


@dataclass
class ProtectedTypeDefinition(_VhdlCstNode):
    definition: ProtectedTypeDeclaration | ProtectedTypeBody

    def format(self):
        return f"{self.definition}"


@dataclass
class TypeDefinition(_VhdlCstNode):
    definition: (
        ScalarTypeDefinition
        | CompositeTypeDefinition
        | AccessTypeDefinition
        | FileTypeDefinition
        | ProtectedTypeDefinition
    )

    def format(self):
        return str(self.definition)


@dataclass
class SubtypeDeclaration(_VhdlCstNode):
    identifier: Identifier
    subtype_indication: SubtypeIndication

    def format(self):
        return f"subtype {self.identifier} is {self.subtype_indication};"


@dataclass
class FullTypeDeclaration(_VhdlCstNode):
    identifier: Identifier
    type_definition: TypeDefinition

    def format(self):
        return f"type {self.identifier} is {self.type_definition};"


@dataclass
class IncompleteTypeDeclaration(_VhdlCstNode):
    identifier: Identifier

    def format(self):
        return str(self.identifier)


@dataclass
class TypeDeclaration(_VhdlCstNode):
    declaration: FullTypeDeclaration | IncompleteTypeDeclaration

    def format(self):
        return str(self.declaration)


@dataclass
class Designator(_VhdlCstNode):
    designator: Identifier | Token

    def format(self):
        return str(self.designator)


@dataclass
class SubprogramHeader(_VhdlCstNode):
    elements: List[GenericInterfaceElement]
    generic_map: GenericMapAspect | None

    def format(self):
        return f"generic({nonestr(self.elements, sep=';'+nl)})" + nonestr(self.generic_map, pre=" ")


@dataclass
class ProcedureSpecification(_VhdlCstNode):
    designator: Designator
    subprogram_header: SubprogramHeader | None
    PARAMETER: Token | None
    formal_parameter_list: List[ParameterInterfaceElement] | None

    def format(self):
        return (
            f"procedure {self.designator}{nonestr(self.subprogram_header, pre=' ')}"
            + nonestr(self.PARAMETER, pre=" ")
            + nonestr(self.formal_parameter_list, pre=" (\n", sep=";\n", post="\n)")
        )


@dataclass
class FunctionSpecification(_VhdlCstNode):
    pure: Token | None
    designator: Designator
    subprogram_header: SubprogramHeader | None
    PARAMETER: Token | None
    formal_parameter_list: List[ParameterInterfaceElement] | None
    type_mark: TypeMark

    def format(self):
        return (
            nonestr(self.pure, post=" ")
            + f"function {self.designator}"
            + nonestr(self.subprogram_header)
            + nonestr(self.PARAMETER, pre=" ")
            + nonestr(self.formal_parameter_list, pre=" (\n", sep=";\n", post="\n)")
            + f" return {self.type_mark}"
        )


@dataclass
class SubprogramSpecification(_VhdlCstNode):
    specification: ProcedureSpecification | FunctionSpecification

    def format(self):
        return str(self.specification)


@dataclass
class SubprogramDeclaration(_VhdlCstNode):
    specification: SubprogramSpecification

    def format(self):
        return str(self.specification) + ";"


@dataclass
class AliasDesignator(_VhdlCstNode):
    designator: Identifier | CharacterLiteral | Token

    def format(self):
        return str(self.designator)


@dataclass
class Signature(_VhdlCstNode):
    types: List[TypeMark] | None
    return_type: TypeMark | None

    def format(self):
        return f"[{nonestr(self.types, sep=', ', post=' ' if self.return_type else '')}{nonestr(self.return_type, pre='return ')}]"


@dataclass
class AliasDeclaration(_VhdlCstNode):
    alias_designator: AliasDesignator
    subtype_indication: SubtypeIndication | None
    name: Name
    signature: Signature | None

    def format(self):
        return f"alias {self.alias_designator}{nonestr(self.subtype_indication, pre=' : ')} is {self.name}{nonestr(self.signature)};"


@dataclass
class PackageDeclarativeItem(_VhdlCstNode):
    item: (
        SubprogramDeclaration
        | SubprogramInstantiationDeclaration
        | PackageDeclaration
        | PackageInstantiationDeclaration
        | TypeDeclaration
        | SubtypeDeclaration
        | ConstantDeclaration
        | SignalDeclaration
        | VariableDeclaration
        | FileDeclaration
        | AliasDeclaration
        | ComponentDeclaration
        | AttributeDeclaration
        | AttributeSpecification
        | UseClause
    )

    def format(self):
        return str(self.item)


@dataclass
class PackageDeclaration(_VhdlCstNode):
    identifier: Identifier
    package_header: PackageHeader
    package_declarative_part: List[PackageDeclarativeItem]
    PACKAGE: Token | None
    package_simple_name: Identifier | None

    def format(self):
        return f"package {self.identifier} is\n{nonestr(self.package_header, post=nl)}{nonestr(self.package_declarative_part, sep=nl)}\nend{nonestr(self.PACKAGE, pre=' ')}{nonestr(self.package_simple_name, pre=' ')};"


@dataclass
class ContextDeclaration(_VhdlCstNode):
    identifier: Identifier
    context_clause: ContextClause
    simple_name: Identifier | None

    def format(self):
        return f"context {self.identifier} is {self.context_clause} end context{nonestr(self.simple_name, pre=' ')};"


@dataclass
class PackageInstantiationDeclaration(_VhdlCstNode):
    identifier: Identifier
    uninstantiated_package_name: Name
    generic_map_aspect: GenericMapAspect

    def format(self):
        return f"package {self.identifier} is new {self.uninstantiated_package_name}{nonestr(self.generic_map_aspect, pre=' ')};"


@dataclass
class PrimaryUnit(_VhdlCstNode):
    unit: (
        EntityDeclaration
        | PackageDeclaration
        | PackageInstantiationDeclaration
        | ContextDeclaration
    )

    def format(self):
        return str(self.unit)


@dataclass
class ConstantDeclaration(_VhdlCstNode):
    identifiers: List[Identifier]
    subtype_indication: SubtypeIndication
    default: Expression | None

    def format(self):
        return f"constant {nonestr(self.identifiers, sep=', ')} : {self.subtype_indication}{nonestr(self.default, pre=' := ')};"


@dataclass
class SignalDeclaration(_VhdlCstNode):
    identifiers: List[Identifier]
    subtype_indication: SubtypeIndication
    kind: Token | None
    default: Expression | None

    def format(self):
        return f"signal {nonestr(self.identifiers, sep=', ')} : {self.subtype_indication}{nonestr(self.kind, pre=' ')}{nonestr(self.default, pre=' := ')};"


@dataclass
class AttributeDeclaration(_VhdlCstNode):
    identifier: Identifier
    type_mark: TypeMark

    def format(self):
        return f"attribute {self.identifier} : {self.type_mark};"


@dataclass
class BlockDeclarativeItem(_VhdlCstNode):
    item: (
        SubprogramDeclaration
        | SubprogramBody
        | SubprogramInstantiationDeclaration
        | PackageDeclaration
        | PackageBody
        | PackageInstantiationDeclaration
        | TypeDeclaration
        | SubtypeDeclaration
        | ConstantDeclaration
        | SignalDeclaration
        | FileDeclaration
        | AliasDeclaration
        | ComponentDeclaration
        | AttributeDeclaration
        | AttributeSpecification
        | UseClause
    )

    def format(self):
        return str(self.item)


@dataclass
class WaveformElement(_VhdlCstNode):
    value: Expression | Token
    time: Expression | None

    def format(self):
        return str(self.value) + nonestr(self.time, pre=" after ")


@dataclass
class Waveform(_VhdlCstListNode):
    element: List[WaveformElement] | Token

    def format(self):
        return nonestr(self.element, sep=", ")


@dataclass
class SelectedWaveforms(_VhdlCstListNode):
    selections: List[Waveform | Choices]

    def format(self):
        vec = [f"{w} when {c}" for w, c in zip(self.selections[0::2], self.selections[1::2])]
        return nonestr(vec, sep=f",\n")


@dataclass
class ConcurrentSelectedSignalAssignment(_VhdlCstNode):
    expression: Expression
    QMARK: Token | None
    target: Target
    GUARDED: Token | None
    delay_mechanism: DelayMechanism | None
    selected_waveforms: SelectedWaveforms

    def format(self):
        return (
            f"with {self.expression} select{nonestr(self.QMARK, pre=' ')}\n"
            + f"{self.target} <= "
            + nonestr(self.GUARDED, post=" ")
            + nonestr(self.delay_mechanism, post=" ")
            + f"\n{self.selected_waveforms};"
        )


@dataclass
class ConditionalWaveforms(_VhdlCstNode):
    waveform: Waveform
    condition: Expression
    conditionals: List[Waveform | Expression]
    else_waveform: Waveform | None

    def format(self):
        vec = [
            f"else {w} when {c}" for w, c in zip(self.conditionals[0::2], self.conditionals[1::2])
        ]
        return f"{self.waveform} when {self.condition}{nonestr(vec, sep=nl)}{nonestr(self.else_waveform, pre=' else ')}"


@dataclass
class ConcurrentConditionalSignalAssignment(_VhdlCstNode):
    target: Target
    GUARDED: Token | None
    delay_mechanism: DelayMechanism | None
    conditional_waveforms: ConditionalWaveforms

    def format(self):
        return (
            f"{self.target} <= "
            + nonestr(self.GUARDED, post=" ")
            + nonestr(self.delay_mechanism, post=" ")
            + f"{self.conditional_waveforms};"
        )


@dataclass
class ConcurrentSimpleSignalAssignment(_VhdlCstNode):
    target: Target
    GUARDED: Token | None
    delay_mechanism: DelayMechanism | None
    waveform: Waveform

    def format(self):
        return (
            f"{self.target} <= "
            + nonestr(self.GUARDED, post=" ")
            + nonestr(self.delay_mechanism, post=" ")
            + f"{self.waveform};"
        )


@dataclass
class ConcurrentSignalAssignmentStatement(_VhdlCstNode):
    label: Identifier | None
    postponed: Token | None
    assignment: (
        ConcurrentSimpleSignalAssignment
        | ConcurrentConditionalSignalAssignment
        | ConcurrentSelectedSignalAssignment
    )

    def format(self):
        return (
            nonestr(self.label, post=": ")
            + nonestr(self.postponed, post=" ")
            + str(self.assignment)
        )


@dataclass
class ProcessSensitivityList(_VhdlCstNode):
    list: Token | List[Name]

    def format(self):
        return nonestr(self.list, sep=", ")


@dataclass
class Target(_VhdlCstNode):
    target: Name | Aggregate

    def format(self):
        return f"{self.target}"


@dataclass
class DelayMechanism(_VhdlCstListNode):
    _list: InitVar[tuple[Token] | tuple[Expression | None, Token]]
    type: Optional[Token] = None
    time_expression: Optional[Expression | None] = None

    def __post_init__(self, _list):
        if isinstance(_list[0], Token):
            super().__setattr__("type", _list[0])
        else:
            super().__setattr__("time_expression", _list[0])
            super().__setattr__("type", _list[1])

    def format(self):
        if self.time_expression:
            return f"reject {self.time_expression} {self.type}"
        else:
            return f"{self.type}"


@dataclass
class SimpleWaveformAssignment(_VhdlCstNode):
    target: Target
    delay: DelayMechanism | None
    waveform: Waveform

    def format(self):
        return f"{self.target} <= {nonestr(self.delay, post=' ')}{self.waveform};"


@dataclass
class SimpleForceAssignment(_VhdlCstNode):
    target: Target
    force_mode: Token | None
    expression: Expression

    def format(self):
        return f"{self.target} <= force {nonestr(self.force_mode, post=' ')}{self.expression};"


@dataclass
class SimpleReleaseAssignment(_VhdlCstNode):
    target: Target
    force_mode: Token | None

    def format(self):
        return f"{self.target} <= release{nonestr(self.force_mode, pre=' ')};"


@dataclass
class SimpleSignalAssignment(_VhdlCstNode):
    item: SimpleWaveformAssignment | SimpleForceAssignment | SimpleReleaseAssignment

    def format(self):
        return str(self.item)


@dataclass
class SignalAssignmentStatement(_VhdlCstNode):
    label: Identifier | None
    assignment: SimpleSignalAssignment  # | ConditionalSignalAssignment | SelectedSignalAssignment

    def format(self):
        return f"{nonestr(self.label, post=': ')}{self.assignment}"


@dataclass
class SimpleVariableAssignment(_VhdlCstNode):
    target: Target
    expression: Expression

    def format(self):
        return f"{self.target} := {self.expression};"


@dataclass
class VariableAssignmentStatement(_VhdlCstNode):
    label: Identifier | None
    assignment: (
        SimpleVariableAssignment  # | ConditionalVariableAssignment | SelectedVariableAssignment
    )

    def format(self):
        return f"{nonestr(self.label, post=': ')}{self.assignment}"


@dataclass
class IfStatement(_VhdlCstNode):
    label: Identifier | None
    condition: Expression
    if_branch_statements: List[SequentialStatement]
    elsif_branches: List[Expression | List[SequentialStatement]]
    else_branch_statements: List[SequentialStatement] | None
    label_end: Identifier | None

    def format(self):
        elsif = (
            []
            if not self.elsif_branches
            else [
                f"elsif {c} then\n{nonestr(s, sep=nl)}"
                for c, s in zip(self.elsif_branches[0::2], self.elsif_branches[1::2])
            ]
        )
        return f"{nonestr(self.label, post=': ')}if {self.condition} then\n{nonestr(self.if_branch_statements, post=nl, sep=nl)}{nonestr(elsif, sep=nl, post=nl)}{nonestr(self.else_branch_statements, pre='else'+nl, sep=nl, post=nl)}end if{nonestr(self.label_end, pre=' ')};"


@dataclass
class CaseStatementAlternative(_VhdlCstListNode):
    alternatives: List[Choices | List[SequentialStatement]]

    def format(self):
        vec = [
            f"when {c} =>{nonestr(s, sep=nl, pre=nl)}"
            for c, s in zip(self.alternatives[0::2], self.alternatives[1::2])
        ]
        return nonestr(vec, sep=nl, post=nl)


@dataclass
class CaseStatement(_VhdlCstNode):
    label: Identifier | None
    qmark: Token | None
    expression: Expression
    alternatives: List[CaseStatementAlternative]
    qmark_end: Token | None
    label_end: Identifier | None

    def format(self):
        return (
            nonestr(self.label, post=": ")
            + "case"
            + nonestr(self.qmark)
            + " "
            + str(self.expression)
            + " is\n"
            + nonestr(self.alternatives, sep="\n", post="\n")
            + f"end case{nonestr(self.qmark_end)}{nonestr(self.label_end, pre=' ')};"
        )


@dataclass
class ConditionClause(_VhdlCstNode):
    condition: Expression

    def format(self):
        return f"until {self.condition}"


@dataclass
class WaitStatement(_VhdlCstNode):
    label: Identifier | None
    sensitivity_clause: List[Name] | None
    condition_clause: ConditionClause | None
    timeout_clause: Expression | None

    def format(self):
        return (
            nonestr(self.label, post=": ")
            + "wait"
            + nonestr(self.sensitivity_clause, sep=", ", pre=" on ")
            + nonestr(self.condition_clause, pre=" ")
            + nonestr(self.timeout_clause, pre=" for ")
            + ";"
        )


@dataclass
class Assertion(_VhdlCstNode):
    condition: Expression
    report: Expression | None
    severity: Expression | None

    def format(self):
        return (
            f"assert {self.condition}"
            + nonestr(self.report, pre="\nreport ")
            + nonestr(self.severity, pre="\nseverity ")
        )


@dataclass
class AssertionStatement(_VhdlCstNode):
    label: Identifier | None
    assertion: Assertion

    def format(self):
        return f"{nonestr(self.label, post=': ')}{self.assertion};"


@dataclass
class ProcedureCall(_VhdlCstNode):
    procedure_name: Name
    actual_parameter_part: List[AssociationElement] | None

    def format(self):
        return f"{self.procedure_name}{nonestr(self.actual_parameter_part, sep=', ', pre='(', post=')')}"


@dataclass
class ProcedureCallStatement(_VhdlCstNode):
    label: Identifier | None
    procedure_call: ProcedureCall

    def format(self):
        return f"{nonestr(self.label, post=': ')}{self.procedure_call};"


@dataclass
class ReturnStatement(_VhdlCstNode):
    label: Identifier | None
    expression: Expression | None

    def format(self):
        return f"{nonestr(self.label, post=': ')}return {nonestr(self.expression)};"


@dataclass
class ParameterSpecification(_VhdlCstNode):
    identifier: Identifier
    discrete_range: DiscreteRange

    def format(self):
        return f"{self.identifier} in {self.discrete_range}"


@dataclass
class IterationScheme(_VhdlCstNode):
    spec: Expression | ParameterSpecification

    def format(self):
        if isinstance(self.spec, Expression):
            return f"while {self.spec}"
        else:
            return f"for {self.spec}"


@dataclass
class LoopStatement(_VhdlCstNode):
    loop_label: Identifier | None
    iteration_scheme: IterationScheme | None
    sequence_of_statements: List[SequentialStatement]
    loop_label_end: Identifier | None

    def format(self):
        return f"{nonestr(self.loop_label, post=': ')}{nonestr(self.iteration_scheme, post=' ')}loop{nonestr(self.sequence_of_statements, pre=nl, sep=nl)}\nend loop{nonestr(self.loop_label_end, pre=' ')};"


@dataclass
class ExitStatement(_VhdlCstNode):
    label: Identifier | None
    loop_label: Identifier | None
    condition: Expression | None

    def format(self):
        return f"{nonestr(self.label, post=': ')}exit{nonestr(self.loop_label, pre=' ')}{nonestr(self.condition, pre=' when ')};"


@dataclass
class ReportStatement(_VhdlCstNode):
    label: Identifier | None
    expression: Expression
    severity: Expression | None

    def format(self):
        return f"{nonestr(self.label, post=': ')}report {self.expression}{nonestr(self.severity, pre=' severity ')};"



@dataclass
class NextStatement(_VhdlCstNode):
    label: Identifier | None
    loop_label: Identifier | None
    condition: Expression | None

    def format(self):
        return f"{nonestr(self.label, post=': ')}next{nonestr(self.loop_label, pre=' ')}{nonestr(self.condition, pre=' when ')};"


@dataclass
class NullStatement(_VhdlCstNode):
    label: Identifier | None

    def format(self):
        return f"{nonestr(self.label, post=': ')}null;"


@dataclass
class SequentialStatement(_VhdlCstNode):
    item: (
        WaitStatement
        | AssertionStatement
        | ReportStatement
        | SignalAssignmentStatement
        | VariableAssignmentStatement
        | ProcedureCallStatement
        | IfStatement
        | CaseStatement
        | LoopStatement
        | NextStatement
        | ExitStatement
        | ReturnStatement
        | NullStatement
    )

    def format(self):
        return str(self.item)


@dataclass
class ProcessStatement(_VhdlCstNode):
    process_label: Identifier | None
    POSTPONED: Token | None
    process_sensitivity_list: ProcessSensitivityList | None
    IS: Token | None
    process_declarative_part: List[ProcessDeclarativeItem] | None
    process_statement_part: List[SequentialStatement] | None
    POSTPONED_end: Token | None
    process_label_end: Identifier | None

    def format(self):
        return (
            f"{nonestr(self.process_label, post=': ')}{nonestr(self.POSTPONED, post=' ')}process{nonestr(self.process_sensitivity_list, pre='(', post=')')}{nonestr(self.IS, pre=' ')}\n"
            + nonestr(self.process_declarative_part, sep="\n", post="\n")
            + "begin\n"
            + nonestr(self.process_statement_part, sep="\n", post="\n")
            + f"end{nonestr(self.POSTPONED_end, pre=' ')} process{nonestr(self.process_label_end, pre=' ')};"
        )


@dataclass
class InstantiatedComponent(_VhdlCstNode):
    component_name: Name

    def format(self):
        return f"component {self.component_name}"


@dataclass
class InstantiatedEntity(_VhdlCstNode):
    entity_name: Name
    architecture_identifier: Identifier | None

    def format(self):
        return f"entity {self.entity_name}" + nonestr(
            self.architecture_identifier, pre="(", post=")"
        )


@dataclass
class InstantiatedConfiguration(_VhdlCstNode):
    component_name: Name

    def format(self):
        return f"configuration {self.component_name}"


InstantiatedUnit = InstantiatedComponent | InstantiatedEntity | InstantiatedConfiguration


@dataclass
class ComponentInstantiationStatement(_VhdlCstNode):
    label: Identifier
    unit: InstantiatedUnit
    generic_map: GenericMapAspect | None
    port_map: PortMapAspect | None

    def format(self):
        return (
            f"{self.label}: {self.unit}\n"
            + nonestr(self.generic_map)
            + nonestr(self.port_map, pre=" " if self.generic_map else "")
            + ";"
        )


@dataclass
class BlockHeader(_VhdlCstNode):
    generic_clause: GenericClause | None
    generic_map_aspect: GenericMapAspect | None
    port_clause: PortClause | None
    port_map_aspect: PortMapAspect | None

    def format(self):
        return (
            nonestr(self.generic_clause)
            + nonestr(self.generic_map_aspect, post=";")
            + nonestr(self.port_clause)
            + nonestr(self.port_map_aspect, post=";")
        )


@dataclass
class BlockStatement(_VhdlCstNode):
    label: Identifier
    guard_condition: Expression | None
    IS: Token | None
    block_header: BlockHeader
    block_declarative_part: List[BlockDeclarativeItem]
    block_statement_part: List[ConcurrentStatement]
    label_end: Identifier | None

    def format(self):
        return (
            f"{self.label}: block"
            + nonestr(self.guard_condition, pre=" (", post=")")
            + nonestr(self.IS, pre=" ")
            + "\n"
            + nonestr(self.block_header)
            + nonestr(self.block_declarative_part, sep="\n")
            + "\nbegin\n"
            + nonestr(self.block_statement_part, sep="\n")
            + "\nend block"
            + nonestr(self.label_end, pre=" ")
            + ";"
        )


@dataclass
class GenerateStatementBody(_VhdlCstNode):
    block_declarative_part: List[BlockDeclarativeItem] | None
    block_statement_part: List[ConcurrentStatement]
    alternative_label: Identifier | None

    def format(self):
        return (
            nonestr(self.block_declarative_part, sep="\n", post=" begin")
            + nonestr(self.block_statement_part, sep="\n", end="\n")
            + nonestr(self.alternative_label, pre="end ", post=";")
        )


@dataclass
class ForGenerateStatement(_VhdlCstNode):
    label: Identifier
    generate_parameter_specification: ParameterSpecification
    generate_statement_body: GenerateStatementBody
    label_end: Identifier | None

    def format(self):
        return (
            f"{self.label}: for {self.generate_parameter_specification} generate\n"
            + f"{self.generate_statement_body}\nend generate{nonestr(self.label_end, post=' ')};"
        )


@dataclass
class IfGenerateStatement(_VhdlCstNode):
    label: Identifier
    if_label: Identifier | None
    condition: Expression
    if_body: GenerateStatementBody
    elsif_branches: List[Identifier | Expression | GenerateStatementBody]
    else_label: Identifier | None
    else_body: GenerateStatementBody | None
    label_end: Identifier | None

    def format(self):
        elsif = (
            []
            if not self.elsif_branches
            else [
                f"elsif {nonestr(l, post=": ")}{c} generate\n{nonestr(b, sep=nl)}"
                for l, c, b in zip(self.elsif_branches[0::3], self.elsif_branches[1::3], self.elsif_branches[2::3])
            ]
        )
        return (
            f"{self.label}: if"
            + nonestr(self.if_label, post=": ")
            + f"{self.condition} generate\n{self.if_body}\n"
            + nonestr(elsif, sep="\n", post="\n")
            + nonestr(self.else_body, pre=f"else {self.else_label} generate\n")
            + f"end generate{nonestr(self.label_end, pre=' ')};"
        )


@dataclass
class CaseGenerateAlternative(_VhdlCstNode):
    label: Identifier
    choices: Choices
    body: GenerateStatementBody

    def format(self):
        return (
            f"when {nonestr(self.label, post=": ")}{self.choices} => {self.body}"
        )


@dataclass
class CaseGenerateStatement(_VhdlCstNode):
    label: Identifier
    expression: Expression
    alternatives: List[CaseGenerateAlternative]
    label_end: Identifier

    def format(self):
        return (
            f"{self.label}: case {self.expression} generate\n"
            + nonestr(self.alternatives, sep='\n', post='\n')
            + f"end generate{nonestr(self.label_end, pre=' ')};"
        )


@dataclass
class ConcurrentProcedureCallStatement(_VhdlCstNode):
    label: Identifier | None
    POSTPONED: Token | None
    procedure_call: ProcedureCall

    def format(self):
        return (
            nonestr(self.label, post=": ") + nonestr(self.POSTPONED, post=' ') + str(self.procedure_call) + ";"
        )


@dataclass
class ConcurrentAssertionStatement(_VhdlCstNode):
    label: Identifier | None
    POSTPONED: Token | None
    assertion: Assertion

    def format(self):
        return (
            nonestr(self.label, post=": ") + nonestr(self.POSTPONED, post=' ') + str(self.assertion) + ";"
        )


GenerateStatement = ForGenerateStatement | IfGenerateStatement | CaseGenerateStatement


@dataclass
class ConcurrentStatement(_VhdlCstNode):
    item: (
        BlockStatement
        | ProcessStatement
        | ConcurrentProcedureCallStatement
        | ConcurrentAssertionStatement
        | ConcurrentSignalAssignmentStatement
        | ComponentInstantiationStatement
        | GenerateStatement
    )

    def format(self):
        return str(self.item)


ArchitectureDeclarativePart = List[BlockDeclarativeItem]
ArchitectureStatementPart = List[ConcurrentStatement]


@dataclass
class ArchitectureBody(_VhdlCstNode):
    identifier: Identifier
    entity_name: Name
    architecture_declarative_part: ArchitectureDeclarativePart | None
    architecture_statement_part: ArchitectureStatementPart | None
    ARCHITECTURE: Token | None
    architecture_simple_name: Identifier | None

    def format(self):
        return (
            f"architecture {self.identifier} of {self.entity_name} is\n{nonestr(self.architecture_declarative_part, sep=nl, post=nl)}begin\n"
            + nonestr(self.architecture_statement_part, sep="\n", post="\n")
            + f"end{nonestr(self.ARCHITECTURE, pre=' ')}{nonestr(self.architecture_simple_name, pre=' ')};\n"
        )


@dataclass
class VariableDeclaration(_VhdlCstNode):
    shared: Token | None
    identifiers: List[Identifier]
    subtype_indication: SubtypeIndication
    default: Expression | None

    def format(self):
        return f"{nonestr(self.shared, post=' ')}variable {nonestr(self.identifiers, sep=', ')} : {self.subtype_indication}{nonestr(self.default, pre=' := ')};"


@dataclass
class DeclarativeItem(_VhdlCstNode):
    item: (
        SubprogramDeclaration
        | SubprogramBody
        | PackageDeclaration
        | PackageBody
        | TypeDeclaration
        | SubtypeDeclaration
        | ConstantDeclaration
        | VariableDeclaration
        | FileDeclaration
        | AliasDeclaration
        | AttributeSpecification
        | UseClause
    )

    def format(self):
        return str(self.item)


SubprogramDeclarativeItem = DeclarativeItem
PackageBodyDeclarativeItem = DeclarativeItem
ProcessDeclarativeItem = DeclarativeItem
ProtectedTypeBodyDeclarativeItem = DeclarativeItem


@dataclass
class SubprogramBody(_VhdlCstNode):
    specification: SubprogramSpecification
    declarative_part: List[SubprogramDeclarativeItem]
    statement_part: List[SequentialStatement]
    kind: Token | None
    designator: Designator | None

    def format(self):
        return f"{self.specification} is\n{nonestr(self.declarative_part, sep=nl)}\nbegin\n{nonestr(self.statement_part, sep=nl)}\nend{nonestr(self.kind, pre=' ')}{nonestr(self.designator, pre=' ')};"


@dataclass
class PackageBody(_VhdlCstNode):
    simple_name: Identifier
    declarative_part: List[PackageBodyDeclarativeItem] | None
    PACKAGE: Token | None
    simple_name_end: Identifier | None

    def format(self):
        return f"package body {self.simple_name} is\n{nonestr(self.declarative_part, sep=nl)}\nend{nonestr(self.PACKAGE, pre=' ', post=' body')}{nonestr(self.simple_name_end, pre=' ')};"


@dataclass
class SecondaryUnit(_VhdlCstNode):
    body: ArchitectureBody | PackageBody

    def format(self):
        return str(self.body)


@dataclass
class LibraryUnit(_VhdlCstNode):
    unit: PrimaryUnit | SecondaryUnit

    def format(self):
        return str(self.unit)


@dataclass
class DesignUnit(_VhdlCstNode):
    context_clause: ContextClause
    library_unit: LibraryUnit

    def format(self):
        return nonestr(self.context_clause, post="\n") + str(self.library_unit)


@dataclass
class DesignFile(_VhdlCstListNode):
    design_units: List[DesignUnit]

    def format(self):
        return nonestr(self.design_units, sep=f"\n")


@dataclass
class ToolDirective(_VhdlCstNode):
    identifier: Identifier
    value: Token | None

    def format(self):
        return f"`{self.identifier}{nonestr(self.value, pre=' ')}"


@dataclass
class EncryptedDesignFile(_VhdlCstListNode):
    directives: List[ToolDirective | Token]

    def format(self):
        return nonestr(self.directives, sep=f"\n")
