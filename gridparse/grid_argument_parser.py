import argparse
import warnings
from typing import Any, Tuple, List, Optional, Union, Sequence
from copy import deepcopy

from gridparse.utils import list_as_dashed_str, strbool


# overwritten to fix issue in __call__
class _GridSubparsersAction(argparse._SubParsersAction):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,  # contains only subparser arg
        values: Optional[
            Union[str, Sequence[Any]]
        ],  # contains all args for gridparse
        option_string: Optional[str] = None,
    ) -> None:
        parser_name = values[0]
        arg_strings = values[1:]

        # set the parser name if requested
        if self.dest is not argparse.SUPPRESS:
            setattr(namespace, self.dest, parser_name)

        # select the parser
        try:
            parser = self._name_parser_map[parser_name]
        except KeyError:
            args = {
                'parser_name': parser_name,
                'choices': ', '.join(self._name_parser_map),
            }
            msg = (
                argparse._(
                    'unknown parser %(parser_name)r (choices: %(choices)s)'
                )
                % args
            )
            raise argparse.ArgumentError(self, msg)

        # parse all the remaining options into the namespace
        # store any unrecognized options on the object, so that the top
        # level parser can decide what to do with them

        # In case this subparser defines new defaults, we parse them
        # in a new namespace object and then update the original
        # namespace for the relevant parts.
        # NOTE: changed here because parser.parse_args() now returns a list
        # of namespaces instead of a single namespace

        namespaces = []

        subnamespaces, arg_strings = parser.parse_known_args(arg_strings, None)
        for subnamespace in subnamespaces:
            new_namespace = deepcopy(namespace)
            for key, value in vars(subnamespace).items():
                setattr(new_namespace, key, value)
            namespaces.append(new_namespace)

        if arg_strings:
            for ns in namespaces:
                vars(ns).setdefault(argparse._UNRECOGNIZED_ARGS_ATTR, [])
                getattr(ns, argparse._UNRECOGNIZED_ARGS_ATTR).extend(
                    arg_strings
                )

        # hacky way to return all namespaces in subparser
        # method is supposed to perform in-place modification
        # of namespace, so we add a new attribute
        namespace.___namespaces___ = namespaces


# overwritten to include our _SubparserAction
class _GridActionsContainer(argparse._ActionsContainer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register("action", "parsers", _GridSubparsersAction)


class GridArgumentParser(_GridActionsContainer, argparse.ArgumentParser):
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

    def parse_args(self, *args, **kwargs):
        vals = super().parse_args(*args, **kwargs)
        # hacky way to return namespaces in subparser
        if "___namespaces___" in vals[0]:
            vals = vals[0].___namespaces___

        # get unrecognized arguments from other namespaces
        if hasattr(vals[0], argparse._UNRECOGNIZED_ARGS_ATTR):
            argv = getattr(vals[0], argparse._UNRECOGNIZED_ARGS_ATTR)
            msg = argparse._("unrecognized arguments: %s")
            self.error(msg % " ".join(argv))

        for ns in vals:
            # get defaults from other arguments
            for arg in dir(ns):
                val = getattr(ns, arg)
                if isinstance(val, str) and val.startswith("args."):
                    borrow_arg = val.split("args.")[1]
                    setattr(ns, arg, getattr(ns, borrow_arg, None))

        is_grid_search = len(self._grid_args) > 0

        for potential_subparser in getattr(
            self._subparsers, "_group_actions", []
        ):
            try:
                grid_args = next(
                    iter(potential_subparser.choices.values())
                )._grid_args
                is_grid_search = is_grid_search or grid_args
            except AttributeError:
                continue

        if len(vals) == 1 and not is_grid_search:
            return vals[0]
        return vals
    
    def _check_value(self, action, value):
        # converted value must be one of the choices (if specified)
        if action.choices is not None and (value not in action.choices and value is not None):
            args = {'value': value,
                    'choices': ', '.join(map(repr, action.choices))}
            msg = argparse._('invalid choice: %(value)r (choose from %(choices)s)')
            raise argparse.ArgumentError(action, msg % args)

    def _get_value(self, action, arg_string):
        """Overwrites `_get_value` to support grid search.
        It is used to parse the value of an argument.
        """
        type_func = self._registry_get('type', action.type, action.type)
        default = action.default

        # if default is "args.X" value,
        # then set up value so that X is grabbed from the same namespace later
        if (isinstance(default, str) and default.startswith("args.")) and (
            default == arg_string or arg_string is None
        ):
            return default
    
        # if arg_string is "args.X" value,
        # then set up value so that X is grabbed from the same namespace later
        if arg_string.startswith("args."):
            return arg_string
        
        # if arg_string is "_None_", then return None
        if (
            arg_string == "_None_"
            and action.dest in self._grid_args
            and action.type is not strbool
        ):
            return None

        if not callable(type_func):
            msg = argparse._('%r is not callable')
            raise argparse.ArgumentError(action, msg % type_func)

        # convert the value to the appropriate type
        try:
            result = type_func(arg_string)

        # ArgumentTypeErrors indicate errors
        except argparse.ArgumentTypeError:
            name = getattr(action.type, '__name__', repr(action.type))
            msg = str(argparse._sys.exc_info()[1])
            raise argparse.ArgumentError(action, msg)

        # TypeErrors or ValueErrors also indicate errors
        except (TypeError, ValueError):
            name = getattr(action.type, '__name__', repr(action.type))
            args = {'type': name, 'value': arg_string}
            msg = argparse._('invalid %(type)s value: %(value)r')
            raise argparse.ArgumentError(action, msg % args)

        # return the converted value
        return result

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

        type = kwargs.get("type", None)
        if type is not None and type == bool:
            kwargs["type"] = strbool

        type = kwargs.get("type", None)
        if type is not None and type == strbool:
            kwargs.setdefault("default", "false")

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

        # doesn't add `searchable` in _StoreAction
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

            if 0 not in self.layers:
                # we get weird behavior if no root-level arguments are given
                # so we add an empty list to the root layer
                self.layers[0] = [[]]

            def recursive_path(depth: int, node: int):
                """Recursively parses all paths from the given node."""
                if depth > max(self.layers.keys()):
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

        # if { and } denote a subspace and not inside a string of something else
        new_arg_strings = []
        for arg in arg_strings:
            new_args = [None, arg, None]

            # find leftmost { and rightmost }
            idx_ocb = arg.find("{")
            idx_ccb = arg.rfind("}")

            cnt = 0
            for i in range(len(arg)):
                if arg[i] == "{":
                    cnt += 1
                elif arg[i] == "}":
                    cnt -= 1

            # if arg starts with { and end with }, doesn't have a },
            # or has at least an extra {, then it's a subspace
            if idx_ocb == 0 and (idx_ccb in (len(arg) - 1, -1) or cnt > 0):
                new_args[0] = "{"
                new_args[1] = new_args[1][1:]
            elif idx_ocb == 0 and cnt <= 0:
                warnings.warn(
                    "Found { at the beginning and some } in the middle "
                    f"of the argument: `{arg}`."
                    " This is not considered a \{\} subspace."
                )
            # if arg ends with } and doesn't have a {, starts with {,
            # or has at least an extra }, then it's a subspace
            if idx_ccb == len(arg) - 1 and (idx_ocb in (0, -1) or cnt < 0):
                new_args[1] = new_args[1][:-1]
                new_args[2] = "}"
            elif idx_ccb == len(arg) - 1 and cnt >= 0:
                warnings.warn(
                    "Found } at the end and some { in the middle "
                    f"of argument: `{arg}`."
                    " This is not considered a \{\} subspace."
                )

            new_arg_strings.extend([a for a in new_args if a])

        arg_strings = new_arg_strings

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
