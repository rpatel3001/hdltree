from itertools import zip_longest
import pydot

from .VhdlCstTransformer import EntityDeclaration, InterfaceIncompleteTypeDeclaration, InterfaceSubprogramDeclaration

def to_symbol(ent: EntityDeclaration, with_generics=True, with_ports=True):
    if len(ent.generics) + len(ent.ports) == 0:
        return

    dotstr = ""

    if with_generics:
        generics = ent.generics
        for g in generics:
            if not isinstance(g.generic_declaration, (InterfaceIncompleteTypeDeclaration, InterfaceSubprogramDeclaration)):
                for name in g.generic_declaration.identifier_list:
                    dotstr += f"""
                        <tr>
                            <td port="{name.id}" colspan="2" align="left" bgcolor="gray">{name.id}</td>
                        </tr>
                    """

    if with_ports:
        ports = ent.ports
        inports = []
        outports = []
        for p in ports:
            if p.port_declaration.mode is None or p.port_declaration.mode.lower() == "in":
                inports.append(p)
            elif p.port_declaration.mode is not None:
                outports.append(p)
        zipports = zip_longest(inports, outports)
        for p in zipports:
            dotstr += f"""
                <tr>
            """
            if p[0]:
                name = p[0].port_declaration.identifier_list[0].id
                dotstr += f"""
                        <td port="{name}" align="left">{name}</td>
                """
            else:
                dotstr += f"""
                        <td></td>
                """
            if p[1]:
                name = p[1].port_declaration.identifier_list[0].id
                dotstr += f"""
                        <td port="{name}" align="right">{name}</td>
                """
            else:
                dotstr += f"""
                        <td></td>
                """
            dotstr += f"""
                </tr>
            """

    if dotstr:
        dotstr = f"""
        digraph MyGraph {{
            rankdir="LR"
            edge [arrowhead=none]
            node [shape=plain]
            a [shape=plain,label=<
                <table border="0" cellborder="1" cellspacing="0" cellpadding="10">
                    {dotstr}
                </table>
            >]
        """

        if with_generics:
            for g in generics:
                if not isinstance(g.generic_declaration, (InterfaceIncompleteTypeDeclaration, InterfaceSubprogramDeclaration)):
                    stype = g.generic_declaration.subtype_indication
                    for name in g.generic_declaration.identifier_list:
                        dotstr += f"""
                            g_{name}[label="{stype}    "]
                            g_{name}:e -> a:{name.id}
                        """

        if with_ports:
            for p in inports:
                name = p.port_declaration.identifier_list[0].id
                stype = p.port_declaration.subtype_indication
                dotstr += f"""
                    p_{name}[label="    {stype}"]
                    p_{name}:e -> a:{name}
                """
            for p in outports:
                name = p.port_declaration.identifier_list[0].id
                stype = p.port_declaration.subtype_indication
                dotstr += f"""
                    p_{name}[label="    {stype}"]
                    a:{name} -> p_{name}:w
                """

        dotstr += """
        }
        """

        #print(dotstr)
        graphs = pydot.graph_from_dot_data(dotstr)
        graph = graphs[0]
        #print(graph.to_string())
        graph.write_svg(f"{ent.identifier}.svg")
