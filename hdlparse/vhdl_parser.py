# -*- coding: utf-8 -*-
# Copyright © 2017 Kevin Thibedeau
# Distributed under the terms of the MIT license
"""VHDL documentation parser"""

import ast
import io
import os
import re
from pprint import pprint
from typing import Any, Dict, List, Optional, Set

from hdltree.hdltree import VhdlParser
from hdltree.VhdlCstTransformer import *

parser = VhdlParser()

class VhdlObject:
    """Base class for parsed VHDL objects

    Args:
      name (str): Name of the object
      desc (str): Description from object metacomments
    """

    def __init__(self, name, desc=None):
        self.name = name
        self.kind = 'unknown'
        self.desc = desc


def remove_outer_parenthesis(s: Optional[str]):
    if s:
        n = 1
        while n:
            s, n = re.subn(r'\([^()]*\)', '', s.strip())  # remove non-nested/flat balanced parts
    return s


class VhdlParameterType:
    """Parameter type definition

    Args:
      name (str): Name of the type
      direction(str): "to" or "downto"
      r_bound (str): A simple expression based on digits or variable names
      l_bound (str): A simple expression based on digits or variable names
      arange (str): Original array range string
    """

    def __init__(self, name, direction="", r_bound="", l_bound="", arange=""):
        self.name = name
        self.direction = direction.lower().strip()
        self.r_bound = r_bound
        self.l_bound = l_bound
        self.arange = arange

    def __repr__(self):
        return f"VhdlParameterType('{self.name}','{self.arange}')"


class VhdlParameter:
    """Parameter to subprograms, ports, and generics

    Args:
      name (str): Name of the object
      mode (optional str): Direction mode for the parameter
      data_type (optional VhdlParameterType): Type name for the parameter
      default_value (optional str): Default value of the parameter
      desc (optional str): Description from object metacomments
      param_desc (optional str): Description of the parameter
    """

    def __init__(self, name, mode: Optional[str] = None, data_type: Optional[VhdlParameterType] = None, default_value: Optional[str] = None, desc: Optional[str] = None):
        self.name = name
        self.mode = mode
        self.data_type = data_type
        self.default_value = default_value
        self.desc = desc
        self.param_desc = None

    def __str__(self):
        if self.mode is not None:
            param = f"{self.name} : {self.mode} {self.data_type.name + self.data_type.arange}"
        else:
            param = f"{self.name} : {self.data_type.name + self.data_type.arange}"

        if self.default_value is not None:
            param = f"{param} := {self.default_value}"

        if self.param_desc is not None:
            param = f"{param} --{self.param_desc}"

        return param

    def __repr__(self):
        return f"VhdlParameter('{self.name}', '{self.mode}', '{self.data_type.name + self.data_type.arange}')"


class VhdlPackage(VhdlObject):
    """Package declaration

    Args:
      name (str): Name of the package
      desc (str): Description from object metacomments
    """

    def __init__(self, name, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'package'


class VhdlType(VhdlObject):
    """Type definition

    Args:
      name (str): Name of the type
      package (str): Package containing the type
      type_of (str): Object type of this type definition
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, type_of, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'type'
        self.package = package
        self.type_of = type_of

    def __repr__(self):
        return f"VhdlType('{self.name}', '{self.type_of}')"


class VhdlSubtype(VhdlObject):
    """Subtype definition

    Args:
      name (str): Name of the subtype
      package (str): Package containing the subtype
      base_type (str): Base type name derived from
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, base_type, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'subtype'
        self.package = package
        self.base_type = base_type

    def __repr__(self):
        return f"VhdlSubtype('{self.name}', '{self.base_type}')"


class VhdlConstant(VhdlObject):
    """Constant definition

    Args:
      name (str): Name of the constant
      package (str): Package containing the constant
      base_type (str): Type fo the constant
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, base_type, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'constant'
        self.package = package
        self.base_type = base_type

    def __repr__(self):
        return f"VhdlConstant('{self.name}', '{self.base_type}')"


class VhdlFunction(VhdlObject):
    """Function declaration

    Args:
      name (str): Name of the function
      package (str): Package containing the function
      parameters (list of VhdlParameter): Parameters to the function
      return_type (str, optional): Type of the return value
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, parameters, return_type=None, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'function'
        self.package = package
        self.parameters = parameters
        self.return_type = return_type

    def __repr__(self):
        return f"VhdlFunction('{self.name}')"


class VhdlProcedure(VhdlObject):
    """Procedure declaration

    Args:
      name (str): Name of the procedure
      package (str): Package containing the procedure
      parameters (list of VhdlParameter): Parameters to the procedure
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, parameters, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'procedure'
        self.package = package
        self.parameters = parameters

    def __repr__(self):
        return f"VhdlProcedure('{self.name}')"


class VhdlEntity(VhdlObject):
    """Entity declaration

    Args:
      name (str): Name of the entity
      ports (list of VhdlParameter): Port parameters to the entity
      generics (list of VhdlParameter): Generic parameters to the entity
      sections (list of str): Metacomment sections
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name: str, ports: List[VhdlParameter], generics: Optional[List[VhdlParameter]] = None, sections: Optional[List[str]] = None, desc: Optional[str] = None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'entity'
        self.generics = generics if generics else []
        self.ports = ports
        self.sections = sections if sections else {}

    def __repr__(self):
        return f"VhdlEntity('{self.name}')"

    def dump(self):
        print(f"VHDL entity: {self.name}")
        for port in self.ports:
            print(f"\t{port.name} ({type(port.name)}), {port.data_type} ({type(port.data_type)})")


class VhdlComponent(VhdlObject):
    """Component declaration

    Args:
      name (str): Name of the component
      package (str): Package containing the component
      ports (list of VhdlParameter): Port parameters to the component
      generics (list of VhdlParameter): Generic parameters to the component
      sections (list of str): Metacomment sections
      desc (str, optional): Description from object metacomments
    """

    def __init__(self, name, package, ports, generics=None, sections=None, desc=None):
        VhdlObject.__init__(self, name, desc)
        self.kind = 'component'
        self.package = package
        self.generics = generics if generics is not None else []
        self.ports = ports
        self.sections = sections if sections is not None else {}

    def __repr__(self):
        return f"VhdlComponent('{self.name}')"

    def dump(self):
        print(f"VHDL component: {self.name}")
        for port in self.ports:
            print(f"\t{port.name} ({type(port.name)}), {port.data_type} ({type(port.data_type)})")


def parse_vhdl_file(fname):
    """Parse a named VHDL file

    Args:
      fname(str): Name of file to parse
    Returns:
      Parsed objects.
    """
    with open(fname, 'rt', encoding='latin-1') as fh:
        text = fh.read()
    return parse_vhdl(text)


def parse_vhdl(text):
    """Parse a text buffer of VHDL code

    Args:
      text(str): Source code to parse
    Returns:
      Parsed objects.
    """
    cst = parser.parse(text)

    objects = []

    for node in cst.iter_subtrees_topdown():
        if isinstance(node, SubprogramDeclaration):
            spec = node.specification.specification
            if isinstance(spec, ProcedureSpecification):
                kind = 'procedure'
            else:
                kind = 'function'
            name = str(spec.designator)
            parameters = []
            for param in spec.formal_parameter_list:
              decl = param.parameter_declaration
              for id in decl.identifier_list:
                default = None
                if decl.default:
                    default = str(decl.default)
                if decl.subtype_indication.constraint and isinstance(decl.subtype_indication.constraint.constraint, ArrayConstraint):
                    ptype = VhdlParameterType(
                        str(decl.subtype_indication.type_mark),
                        decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.direction,
                        str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.right),
                        str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.left),
                        str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range)
                    )
                else:
                    ptype = VhdlParameterType(str(decl.subtype_indication.type_mark))
                parameters += [VhdlParameter(str(id), str(decl.mode) if decl.mode else "in", ptype, default)]

            if kind == 'function':
                vobj = VhdlFunction(name, cur_package, parameters, str(spec.type_mark))
            else:
                vobj = VhdlProcedure(name, cur_package, parameters)
            objects.append(vobj)

        elif isinstance(node, EntityDeclaration):
            if genclause := node.entity_header.generic_clause:
                generics = []
                for elem in genclause.interface_elements:
                    decl = elem.generic_declaration
                    for id in decl.identifier_list:
                        default = None
                        if decl.default:
                            default = str(decl.default)
                        if decl.subtype_indication.constraint and isinstance(decl.subtype_indication.constraint.constraint, ArrayConstraint):
                            ptype = VhdlParameterType(
                                str(decl.subtype_indication.type_mark),
                                decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.direction,
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.right),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.left),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range)
                            )
                        else:
                            ptype = VhdlParameterType(str(decl.subtype_indication.type_mark))
                        generics += [VhdlParameter(str(id), str(decl.mode) if decl.mode else "in", ptype, default)]
            else:
                generics = None

            ports = []
            if portclause := node.entity_header.port_clause:
                for elem in portclause.interface_elements:
                    decl = elem.port_declaration
                    for id in decl.identifier_list:
                        default = None
                        if decl.default:
                            default = str(decl.default)
                        if decl.subtype_indication.constraint and isinstance(decl.subtype_indication.constraint.constraint, ArrayConstraint):
                            ptype = VhdlParameterType(
                                str(decl.subtype_indication.type_mark),
                                decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.direction,
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.right),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.left),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range)
                            )
                        else:
                            ptype = VhdlParameterType(str(decl.subtype_indication.type_mark))
                        ports += [VhdlParameter(str(id), str(decl.mode) if decl.mode else "in", ptype, default)]

            vobj = VhdlEntity(str(node.identifier), ports, generics)
            objects.append(vobj)

        elif isinstance(node, ComponentDeclaration):
            if genclause := node.local_generic_clause:
                generics = []
                for elem in genclause.interface_elements:
                    decl = elem.generic_declaration
                    for id in decl.identifier_list:
                        default = None
                        if decl.default:
                            default = str(decl.default)
                        if decl.subtype_indication.constraint and isinstance(decl.subtype_indication.constraint.constraint, ArrayConstraint):
                            ptype = VhdlParameterType(
                                str(decl.subtype_indication.type_mark),
                                decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.direction,
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.right),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.left),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range)
                            )
                        else:
                            ptype = VhdlParameterType(str(decl.subtype_indication.type_mark))
                        generics += [VhdlParameter(str(id), str(decl.mode) if decl.mode else "in", ptype, default)]
            else:
                generics = None

            ports = []
            if portclause := node.local_port_clause:
                for elem in portclause.interface_elements:
                    decl = elem.port_declaration
                    for id in decl.identifier_list:
                        default = None
                        if decl.default:
                            default = str(decl.default)
                        if decl.subtype_indication.constraint and isinstance(decl.subtype_indication.constraint.constraint, ArrayConstraint):
                            ptype = VhdlParameterType(
                                str(decl.subtype_indication.type_mark),
                                decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.direction,
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.right),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range.left),
                                str(decl.subtype_indication.constraint.constraint.index_constraint.discrete_ranges[0].range)
                            )
                        else:
                            ptype = VhdlParameterType(str(decl.subtype_indication.type_mark))
                        ports += [VhdlParameter(str(id), str(decl.mode) if decl.mode else "in", ptype, default)]
            vobj = VhdlComponent(str(node.identifier), cur_package, ports, generics)
            objects.append(vobj)

        elif isinstance(node, PackageDeclaration):
            cur_package = str(node.identifier)
            objects.append(VhdlPackage(cur_package))

        elif isinstance(node, (FullTypeDeclaration, SubtypeDeclaration)):
            vobj = VhdlType(str(node.identifier), cur_package, str(node.children[1]))
            objects.append(vobj)

        elif isinstance(node, SubtypeDeclaration):
            vobj = VhdlSubtype(str(node.identifier), cur_package, str(node.subtype_indication))
            objects.append(vobj)

        elif isinstance(node, ConstantDeclaration):
            if isinstance(node.parent, PackageDeclarativeItem):
              for id in node.identifiers:
                vobj = VhdlConstant(str(id.id), cur_package, str(node.subtype_indication))
                objects.append(vobj)

    return objects


def subprogram_prototype(vo):
    """Generate a canonical prototype string

    Args:
      vo (VhdlFunction, VhdlProcedure): Subprogram object
    Returns:
      Prototype string.
    """

    plist = '; '.join(str(p) for p in vo.parameters)

    if isinstance(vo, VhdlFunction):
        if len(vo.parameters) > 0:
            proto = f"function {vo.name}({plist}) return {vo.return_type};"
        else:
            proto = f"function {vo.name} return {vo.return_type};"

    else:  # procedure
        proto = f"procedure {vo.name}({plist});"

    return proto


def subprogram_signature(vo, fullname=None):
    """Generate a signature string

    Args:
      vo (VhdlFunction, VhdlProcedure): Subprogram object
      fullname (None, str): Override object name
    Returns:
      Signature string.
    """

    if fullname is None:
        fullname = vo.name

    if isinstance(vo, VhdlFunction):
        plist = ','.join(p.data_type for p in vo.parameters)
        sig = f"{fullname}[{plist} return {vo.return_type}]"
    else:  # procedure
        plist = ','.join(p.data_type for p in vo.parameters)
        sig = f"{fullname}[{plist}]"

    return sig


def is_vhdl(fname):
    """Identify file as VHDL by its extension

    Args:
      fname (str): File name to check
    Returns:
      True when file has a VHDL extension.
    """
    return os.path.splitext(fname)[-1].lower() in ('.vhdl', '.vhd')


class VhdlExtractor:
    """Utility class that caches parsed objects and tracks array type definitions

    Args:
      array_types(set): Initial array types
    """

    def __init__(self, array_types: Set[str] | None = None):
        self.array_types = set(('std_ulogic_vector', 'std_logic_vector',
                                'signed', 'unsigned', 'bit_vector'))
        if array_types:
            self.array_types |= array_types
        self.object_cache: Dict[str, Any] = {}  # Any -> VhdlObject

    def extract_objects(self, fname, type_filter=None):
        """Extract objects from a source file

        Args:
          fname (str): File to parse
          type_filter (class, optional): Object class to filter results
        Returns:
          List of parsed objects.
        """
        objects = []
        if fname in self.object_cache:
            objects = self.object_cache[fname]
        else:
            with io.open(fname, 'rt', encoding='latin-1') as fh:
                text = fh.read()
                objects = parse_vhdl(text)
                self.object_cache[fname] = objects
                self._register_array_types(objects)

        if type_filter:
            if not isinstance(type_filter, list):
                type_filter = [type_filter]

            def type_is_in_filter(obj):
                return any(map(lambda clz: isinstance(obj, clz), type_filter))
            objects = [o for o in objects if type_is_in_filter(o)]

        return objects

    def extract_objects_from_source(self, text, type_filter=None):
        """Extract object declarations from a text buffer

        Args:
          text (str): Source code to parse
          type_filter (class, optional): Object class to filter results
        Returns:
          List of parsed objects.
        """
        objects = parse_vhdl(text)
        self._register_array_types(objects)

        if type_filter:
            objects = [o for o in objects if isinstance(o, type_filter)]

        return objects

    def is_array(self, data_type):
        """Check if a type is a known array type

        Args:
          data_type (str): Name of type to check
        Returns:
          True if ``data_type`` is a known array type.
        """
        return data_type.name.lower() in self.array_types

    def _add_array_types(self, type_defs):
        """Add array data types to internal registry

        Args:
          type_defs (dict): Dictionary of type definitions
        """
        if 'arrays' in type_defs:
            self.array_types |= set(type_defs['arrays'])

    def load_array_types(self, fname):
        """Load file of previously extracted data types

        Args:
          fname (str): Name of file to load array database from
        """
        type_defs = ''
        with open(fname, 'rt', encoding='latin-1') as fh:
            type_defs = fh.read()

        try:
            type_defs = ast.literal_eval(type_defs)
        except SyntaxError:
            type_defs = {}

        self._add_array_types(type_defs)

    def save_array_types(self, fname):
        """Save array type registry to a file

        Args:
          fname (str): Name of file to save array database to
        """
        type_defs = {'arrays': sorted(list(self.array_types))}
        with open(fname, 'wt', encoding='latin-1') as fh:
            pprint(type_defs, stream=fh)

    def _register_array_types(self, objects):
        """Add array type definitions to internal registry

        Args:
          objects (list of VhdlType or VhdlSubtype): Array types to track
        """
        # Add all array types directly
        types = [o for o in objects if isinstance(o, VhdlType) and o.type_of == 'array_type']
        for t in types:
            self.array_types.add(t.name)

        subtypes = {o.name: o.base_type for o in objects if isinstance(o, VhdlSubtype)}

        # Find all subtypes of an array type
        for k, v in subtypes.items():
            while v in subtypes:  # Follow subtypes of subtypes
                v = subtypes[v]
            if v in self.array_types:
                self.array_types.add(k)

    def register_array_types_from_sources(self, source_files):
        """Add array type definitions from a file list to internal registry

        Args:
          source_files (list of str): Files to parse for array definitions
        """
        for fname in source_files:
            if is_vhdl(fname):
                self._register_array_types(self.extract_objects(fname))


def main():
    ve = VhdlExtractor()
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

    objs = ve.extract_objects_from_source(code)

    for o in objs:
        print(o.name)
        try:
            for p in o.parameters:
                print(p)
        except AttributeError:
            pass

        try:
            for p in o.ports:
                print(p)
        except AttributeError:
            pass


if __name__ == '__main__':
    main()
