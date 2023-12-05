import argparse
from typing import Tuple, List
from copy import deepcopy

from gridparse.utils import list_as_dashed_str


class GridArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that supports grid search.

    It transforms the following arguments in the corresponding way:

        --arg 1 -> --arg 1 2 3

        --arg 1 2 3 -> --arg 1~~2~~3 4~~5~~6

        --arg 1-2-3 4-5-6 -> --arg 1-2-3~~4-5-6 7-8-9~~10-11

    So, for single arguments, it extends them similar to nargs="+".
    For multiple arguments, it extends them with
    list_as_dashed_str(type, delimiter="~~"), and this is recursively
    applied with existing list_as_dashed_str types. It can also handle subspaces
    using square brackets, where you can enclose combinations of hyperparameters
    within but don't have them combine with values of hyperparameters in other
    subspaces of the same length.

    Example without subspaces:
        ```
        parser = GridArgumentParser()
        parser.add_argument("--hparam1", type=int, searchable=True)
        parser.add_argument("--hparam2", nargs="+", type=int, searchable=True)
        parser.add_argument("--normal", required=True, type=str)
        parser.add_argument(
            "--lists",
            required=True,
            nargs="+",
            type=list_as_dashed_str(str),
            searchable=True,
        )
        parser.add_argument(
            "--normal_lists",
            required=True,
            nargs="+",
            type=list_as_dashed_str(str),
        )
        args = parser.parse_args(
            (
                "--hparam1 1~~2~~3 --hparam2 4~~3 5~~4 6~~5 "
                "--normal efrgthytfgn --lists 1-2-3 3-4-5~~6-7 "
                "--normal_lists 1-2-3 4-5-6"
            ).split()
        )
        assert len(args) == 1 * 3 * 1 * 2 * 1  # corresponding number of different values in input CL arguments

        pprint(args)
        ```

    Output:
        ```
        [Namespace(hparam1=[1, 2, 3], hparam2=[4, 3], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),
        Namespace(hparam1=[1, 2, 3], hparam2=[5, 4], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),
        Namespace(hparam1=[1, 2, 3], hparam2=[6, 5], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),
        Namespace(hparam1=[1, 2, 3], hparam2=[4, 3], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),
        Namespace(hparam1=[1, 2, 3], hparam2=[5, 4], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),
        Namespace(hparam1=[1, 2, 3], hparam2=[6, 5], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']])]
        ```

    Example with subspaces:
        ```
        parser = GridArgumentParser()
        parser.add_argument("--hparam1", type=int, searchable=True)
        parser.add_argument("--hparam2", type=int, searchable=True)
        parser.add_argument("--hparam3", type=int, searchable=True, default=1000)
        parser.add_argument("--hparam4", type=int, searchable=True, default=2000)
        parser.add_argument("--normal", required=True, type=str)

        args = parser.parse_args(
            (
                "--hparam1 1 2 "
                "{--hparam2 1 2 3 {--normal normal --hparam4 100 101 102} {--normal maybe --hparam4 200 201 202 203}} "
                "{--hparam2 4 5 6 --normal not-normal}"
            ).split()
        )
        assert len(args) == 2 * ((3 * (3 + 4)) + 3)
        ```
    """

    def __init__(self, *args, **kwargs):
        self._grid_args = []
        super().__init__(*args, **kwargs)

    def add_argument(self, *args, **kwargs) -> argparse.Action:
        """Augments `add_argument` to support grid search.
        For parameters that are searchable, provide specification
        for a single value, and set the new argument `searchable`
        to `True`.
        """

        ## copy-pasted code
        chars = self.prefix_chars
        if not args or len(args) == 1 and args[0][0] not in chars:
            if args and "dest" in kwargs:
                raise ValueError("dest supplied twice for positional argument")
            new_kwargs = self._get_positional_kwargs(*args, **kwargs)

        # otherwise, we're adding an optional argument
        else:
            new_kwargs = self._get_optional_kwargs(*args, **kwargs)
        ## edoc detsap-ypoc

        searchable = kwargs.pop("searchable", False)
        if searchable:
            dest = new_kwargs["dest"]
            self._grid_args.append(dest)

            nargs = kwargs.get("nargs", None)
            type = kwargs.get("type", None)

            if nargs == "+":
                type = list_as_dashed_str(type, delimiter="~~")
            else:
                nargs = "+"

            kwargs["nargs"] = nargs
            kwargs["type"] = type

        return super().add_argument(*args, **kwargs)

    class _Tree:
        """Tree data structure to parse grid search arguments.
        Always assumes that last node in each layer is the active one
        (special case in this application)."""

        def __init__(self):
            """Initializes the tree."""
            self.layers = {}
            self.children = {}

        def add_child(self, depth: int):
            """Adds a child to the last node at the given depth.
            This is assigned to the last node of the previous layer."""
            self.layers.setdefault(depth, []).append([])
            if depth > 0:
                children = self.children.setdefault(depth - 1, [])
                if not children:
                    children.append([])
                children[-1].append(len(self.layers[depth]) - 1)

        def add_arg(self, depth, arg):
            """Adds an argument to the last node at the given depth."""
            layer = self.layers.setdefault(depth, [])
            if not layer:
                layer.append([])
            layer[-1].append(arg)

        def parse_paths(self):
            """Parses all leaf-to-root paths by concatenating their values."""

            def recursive_path(depth: int, node: int):
                """Recursively parses all paths from the given node."""
                if depth >= len(self.layers):
                    return []
                children = (
                    self.children[depth][node]
                    if depth in self.children
                    and node < len(self.children[depth])
                    else []
                )

                if not children:
                    return [self.layers[depth][node]]

                child_acc_args = []
                for child in children:
                    paths = recursive_path(depth + 1, child)
                    for path in paths:
                        child_acc_args.append(path + self.layers[depth][node])
                return child_acc_args

            return recursive_path(0, 0)

    def _parse_known_args(
        self, arg_strings: List[str], namespace: argparse.Namespace
    ) -> Tuple[List[argparse.Namespace], List[str]]:
        """Augments `_parse_known_args` to support grid search.
        Different values for the same argument are expanded into
        multiple namespaces.

        Returns:
            A list of namespaces instead os a single namespace.
        """

        # break { and } into separate arguments for easier parsing
        arg_strings = (
            " ".join(arg_strings)
            .replace("}", " } ")
            .replace("{", " { ")
            .split()
        )

        # break arg_strings into subspaces on { and }
        arg_strings_tree = self._Tree()
        sq_br_cnt = 0  # act like a "stack"

        for arg in arg_strings:
            if arg == "{":
                sq_br_cnt += 1
                # adds new child at depth `sq_br_cnt`,
                # which is current active node at that
                # depth until a new child at that depth is created
                # this is assigned to the last active node of the previous layer
                arg_strings_tree.add_child(sq_br_cnt)
            elif arg == "}":
                sq_br_cnt -= 1
            else:
                # adds value to last search subspace in the current depth
                arg_strings_tree.add_arg(sq_br_cnt, arg)

        all_arg_strings = arg_strings_tree.parse_paths()
        all_namespaces = []
        all_args = []

        if not all_arg_strings:
            namespace, args = super()._parse_known_args(
                arg_strings, deepcopy(namespace)
            )
            return [namespace], args

        # for all possible combinations in the grid search subspaces
        for arg_strings in all_arg_strings:
            new_namespace, args = super()._parse_known_args(
                arg_strings, deepcopy(namespace)
            )

            namespaces = [deepcopy(new_namespace)]

            for arg in self._grid_args:
                if not hasattr(new_namespace, arg):
                    continue
                values = getattr(new_namespace, arg)
                for ns in namespaces:
                    ns.__delattr__(arg)
                if not isinstance(values, list):
                    values = [values]

                # duplicate the existing namespaces
                # for all different values of the grid search param

                new_namespaces = []

                for value in values:
                    for ns in namespaces:
                        new_ns = deepcopy(ns)
                        setattr(new_ns, arg, value)
                        new_namespaces.append(new_ns)

                namespaces = new_namespaces

            all_namespaces.extend(namespaces)
            all_args.extend(args)

        return all_namespaces, all_args
