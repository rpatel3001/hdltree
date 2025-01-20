from lark import v_args, Transformer, Visitor, Tree, Token, Discard

class Tokens(Transformer):
    pass
    as_list = list
    # turn terminal tokens into base data types
    # def __default_token__(self, token):
    #  return token.value


class AddCstParent(Visitor):
    def __default__(self, tree):
        for child in tree.children:
            if isinstance(child, Tree):
                assert not hasattr(child, "parent")
                child.parent = tree
            elif isinstance(child, list):
                for listchild in child:
                    listchild.parent = tree
            elif child is None:
                pass
            elif isinstance(child, Token):
                pass
            else:
                print(type(child))
                raise Exception("bad! check this code!")


def is_deleteable(tree):
    if hasattr(tree, "to_delete"):
        return True
    for c in tree.children:
        if isinstance(c, Tree) and is_deleteable(c):
            return True
    return False

def get_unique(children):
    unique = []
    for c in children:
        if c not in unique:
            if not is_deleteable(c):
                unique.append(c)
    return unique


class CountAmbig(Visitor):
    cnt = 0

    def _ambig(self, tree):
        self.cnt += 1
        if self.cnt < 5:
            print(tree.pretty())


class CollapseAmbig(Transformer):
    def _ambig(self, children):
        return Tree(children[0].data, children[0].children)


class MakeAmbigUnique(Transformer):
    #def __default__(self, data, children, meta):
    #    if 0 == len(children):
    #        print(f"pruned empty node {data}")
    #        return Discard
    #    else:
    #        return Tree(data, children, meta)

    #@v_args(tree=True)
    #def as_list(self, tree):
    #    return tree

    def __init__(self, project=None):
        self.project = project


    @v_args(tree=True)
    def _ambig(self, tree):
        numorig = len(tree.children)
        unique = get_unique(tree.children)
        numunique = len(unique)
        if 0 == numunique:
            #print(f"pruned empty ambig node")
            return Discard
        elif 1 == numunique:
            #print(f"disambiguated {numorig} identical branches {unique[0].data}")
            return Tree(unique[0].data, unique[0].children)
        else:
            #if numorig != numunique:
            #    print(f"trimmed {numorig} branches to {numunique}")
            return Tree("_ambig", unique)

    @v_args(tree=True)
    def function_call(self, tree):
        functions = []
        children = tree.children
        while isinstance(children[0], Tree):
            children = children[0].children

        name = children[0].value
        if name not in functions:
            tree.to_delete = True
            return tree
        else:
            return tree


    @v_args(tree=True)
    def physical_literal(self, tree):
        units = ["fs", "ps", "ns", "us", "ms", "sec", "min", "hr"]
        unit = tree.children[1]
        if isinstance(unit, Tree):
            unit = unit.children[0]
        if unit not in units:
            tree.to_delete = True
            return Discard
        else:
            return tree
