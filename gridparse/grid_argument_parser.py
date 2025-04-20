import os
import argparse
import warnings
from typing import Any, Tuple, List, Optional, Union, Sequence
from copy import deepcopy
from omegaconf import OmegaConf

from gridparse.utils import list_as_delim_str, strbool


class AuxArgumentParser(argparse.ArgumentParser):
    """Overwritten only to collect the argument names that
    are specified in the command line."""

    def parse_known_args(
        self, args=None, namespace=None
    ) -> Tuple[argparse.Namespace, List[str]]:
        """Overwritten to collect the argument names that
        are specified in the command line."""
        if args is None:
            # args default to the system args
            args = argparse._sys.argv[1:]
        else:
            # make sure that args are mutable
            args = list(args)

        # default Namespace built from parser defaults
        if namespace is None:
            namespace = argparse.Namespace()

        if not hasattr(namespace, "___specified_args___"):
            setattr(namespace, "___specified_args___", set())

        # add any action defaults that aren't present
        for action in self._actions:
            if action.dest is not argparse.SUPPRESS:
                if not hasattr(namespace, action.dest):
                    if action.default is not argparse.SUPPRESS:
                        setattr(namespace, action.dest, action.default)

        # add any parser defaults that aren't present
        for dest in self._defaults:
            if not hasattr(namespace, dest):
                setattr(namespace, dest, self._defaults[dest])

        # parse the arguments and exit if there are any errors
        if self.exit_on_error:
            try:
                namespace, args = self._parse_known_args(args, namespace)
            except argparse.ArgumentError:
                err = argparse._sys.exc_info()[1]
                self.error(str(err))
        else:
            namespace, args = self._parse_known_args(args, namespace)

        if hasattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR):
            args.extend(getattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR))
            delattr(namespace, argparse._UNRECOGNIZED_ARGS_ATTR)

        return namespace, args

    def _parse_known_args(
        self, arg_strings, namespace
    ) -> Tuple[List[argparse.Namespace], List[str]]:
        """Overwritten to collect the argument names that
        are specified in the command line."""

        # replace arg strings that are file references
        if self.fromfile_prefix_chars is not None:
            arg_strings = self._read_args_from_files(arg_strings)

        # map all mutually exclusive arguments to the other arguments
        # they can't occur with
        action_conflicts = {}
        for mutex_group in self._mutually_exclusive_groups:
            group_actions = mutex_group._group_actions
            for i, mutex_action in enumerate(mutex_group._group_actions):
                conflicts = action_conflicts.setdefault(mutex_action, [])
                conflicts.extend(group_actions[:i])
                conflicts.extend(group_actions[i + 1 :])

        # find all option indices, and determine the arg_string_pattern
        # which has an 'O' if there is an option at an index,
        # an 'A' if there is an argument, or a '-' if there is a '--'
        option_string_indices = {}
        arg_string_pattern_parts = []
        arg_strings_iter = iter(arg_strings)
        for i, arg_string in enumerate(arg_strings_iter):

            # all args after -- are non-options
            if arg_string == '--':
                arg_string_pattern_parts.append('-')
                for arg_string in arg_strings_iter:
                    arg_string_pattern_parts.append('A')

            # otherwise, add the arg to the arg strings
            # and note the index if it was an option
            else:
                option_tuple = self._parse_optional(arg_string)
                if option_tuple is None:
                    pattern = 'A'
                else:
                    option_string_indices[i] = option_tuple
                    pattern = 'O'
                arg_string_pattern_parts.append(pattern)

        # join the pieces together to form the pattern
        arg_strings_pattern = ''.join(arg_string_pattern_parts)

        # converts arg strings to the appropriate and then takes the action
        seen_actions = set()
        seen_non_default_actions = set()

        def take_action(action, argument_strings, option_string=None):
            seen_actions.add(action)
            argument_values = self._get_values(action, argument_strings)

            # error if this argument is not allowed with other previously
            # seen arguments, assuming that actions that use the default
            # value don't really count as "present"
            if argument_values is not action.default:
                seen_non_default_actions.add(action)
                for conflict_action in action_conflicts.get(action, []):
                    if conflict_action in seen_non_default_actions:
                        msg = argparse._('not allowed with argument %s')
                        action_name = argparse._get_action_name(conflict_action)
                        raise argparse.ArgumentError(action, msg % action_name)

            # take the action if we didn't receive a SUPPRESS value
            # (e.g. from a default)
            if argument_values is not argparse.SUPPRESS:
                action(self, namespace, argument_values, option_string)
                namespace.___specified_args___.add(action.dest)

        # function to convert arg_strings into an optional action
        def consume_optional(start_index):

            # get the optional identified at this index
            option_tuple = option_string_indices[start_index]
            action, option_string, explicit_arg = option_tuple

            # identify additional optionals in the same arg string
            # (e.g. -xyz is the same as -x -y -z if no args are required)
            match_argument = self._match_argument
            action_tuples = []
            while True:

                # if we found no optional action, skip it
                if action is None:
                    extras.append(arg_strings[start_index])
                    return start_index + 1

                # if there is an explicit argument, try to match the
                # optional's string arguments to only this
                if explicit_arg is not None:
                    arg_count = match_argument(action, 'A')

                    # if the action is a single-dash option and takes no
                    # arguments, try to parse more single-dash options out
                    # of the tail of the option string
                    chars = self.prefix_chars
                    if (
                        arg_count == 0
                        and option_string[1] not in chars
                        and explicit_arg != ''
                    ):
                        action_tuples.append((action, [], option_string))
                        char = option_string[0]
                        option_string = char + explicit_arg[0]
                        new_explicit_arg = explicit_arg[1:] or None
                        optionals_map = self._option_string_actions
                        if option_string in optionals_map:
                            action = optionals_map[option_string]
                            explicit_arg = new_explicit_arg
                        else:
                            msg = argparse._('ignored explicit argument %r')
                            raise argparse.ArgumentError(
                                action, msg % explicit_arg
                            )

                    # if the action expect exactly one argument, we've
                    # successfully matched the option; exit the loop
                    elif arg_count == 1:
                        stop = start_index + 1
                        args = [explicit_arg]
                        action_tuples.append((action, args, option_string))
                        break

                    # error if a double-dash option did not use the
                    # explicit argument
                    else:
                        msg = argparse._('ignored explicit argument %r')
                        raise argparse.ArgumentError(action, msg % explicit_arg)

                # if there is no explicit argument, try to match the
                # optional's string arguments with the following strings
                # if successful, exit the loop
                else:
                    start = start_index + 1
                    selected_patterns = arg_strings_pattern[start:]
                    arg_count = match_argument(action, selected_patterns)
                    stop = start + arg_count
                    args = arg_strings[start:stop]
                    action_tuples.append((action, args, option_string))
                    break

            # add the Optional to the list and return the index at which
            # the Optional's string args stopped
            assert action_tuples
            for action, args, option_string in action_tuples:
                take_action(action, args, option_string)
            return stop

        # the list of Positionals left to be parsed; this is modified
        # by consume_positionals()
        positionals = self._get_positional_actions()

        # function to convert arg_strings into positional actions
        def consume_positionals(start_index):
            # match as many Positionals as possible
            match_partial = self._match_arguments_partial
            selected_pattern = arg_strings_pattern[start_index:]
            arg_counts = match_partial(positionals, selected_pattern)

            # slice off the appropriate arg strings for each Positional
            # and add the Positional and its args to the list
            for action, arg_count in zip(positionals, arg_counts):
                args = arg_strings[start_index : start_index + arg_count]
                start_index += arg_count
                take_action(action, args)

            # slice off the Positionals that we just parsed and return the
            # index at which the Positionals' string args stopped
            positionals[:] = positionals[len(arg_counts) :]
            return start_index

        # consume Positionals and Optionals alternately, until we have
        # passed the last option string
        extras = []
        start_index = 0
        if option_string_indices:
            max_option_string_index = max(option_string_indices)
        else:
            max_option_string_index = -1
        while start_index <= max_option_string_index:

            # consume any Positionals preceding the next option
            next_option_string_index = min(
                [
                    index
                    for index in option_string_indices
                    if index >= start_index
                ]
            )
            if start_index != next_option_string_index:
                positionals_end_index = consume_positionals(start_index)

                # only try to parse the next optional if we didn't consume
                # the option string during the positionals parsing
                if positionals_end_index > start_index:
                    start_index = positionals_end_index
                    continue
                else:
                    start_index = positionals_end_index

            # if we consumed all the positionals we could and we're not
            # at the index of an option string, there were extra arguments
            if start_index not in option_string_indices:
                strings = arg_strings[start_index:next_option_string_index]
                extras.extend(strings)
                start_index = next_option_string_index

            # consume the next optional and any arguments for it
            start_index = consume_optional(start_index)

        # consume any positionals following the last Optional
        stop_index = consume_positionals(start_index)

        # if we didn't consume all the argument strings, there were extras
        extras.extend(arg_strings[stop_index:])

        # make sure all required actions were present and also convert
        # action defaults which were not given as arguments
        required_actions = []
        for action in self._actions:
            if action not in seen_actions:
                if action.required:
                    required_actions.append(argparse._get_action_name(action))
                else:
                    # Convert action default now instead of doing it before
                    # parsing arguments to avoid calling convert functions
                    # twice (which may fail) if the argument was given, but
                    # only if it was defined already in the namespace
                    if (
                        action.default is not None
                        and isinstance(action.default, str)
                        and hasattr(namespace, action.dest)
                        and action.default is getattr(namespace, action.dest)
                    ):
                        setattr(
                            namespace,
                            action.dest,
                            self._get_value(action, action.default),
                        )

        if required_actions:
            self.error(
                argparse._('the following arguments are required: %s')
                % ', '.join(required_actions)
            )

        # make sure all required groups had one option present
        for group in self._mutually_exclusive_groups:
            if group.required:
                for action in group._group_actions:
                    if action in seen_non_default_actions:
                        break

                # if no actions were used, report the error
                else:
                    names = [
                        argparse._get_action_name(action)
                        for action in group._group_actions
                        if action.help is not argparse.SUPPRESS
                    ]
                    msg = argparse._('one of the arguments %s is required')
                    self.error(msg % ' '.join(names))

        # return the updated namespace, the extra arguments, and the epxlicitly specified args
        return namespace, extras


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
            new_namespace.___specified_args___.update(
                subnamespace.___specified_args___
            )

            for key, value in vars(subnamespace).items():
                if key == "___specified_args___":
                    continue
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


class GridArgumentParser(_GridActionsContainer, AuxArgumentParser):
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

    def __init__(self, retain_config_filename: bool = False, *args, **kwargs):
        """Initializes the GridArgumentParser.

        Args:
            retain_config_filename: whether to keep the `gridparse-config` argument
                in the namespace or not.
        """
        self._grid_args = []
        self._retain_config_filename = retain_config_filename
        super().__init__(*args, **kwargs)
        self.add_argument(
            "--gridparse-config",
            "--gridparse_config",
            type=str,
            nargs="*",
            help="Path to a configuration file with default values for parser. "
            "Values will be used if not provided in the command line.",
        )

    def parse_args(self, *args, **kwargs):
        vals = super().parse_args(*args, **kwargs)

        # hacky way to return namespaces in subparser
        if "___namespaces___" in vals[0]:
            vals = [ns for subps_ns in vals for ns in subps_ns.___namespaces___]

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

        # is_grid_search = len(self._grid_args) > 0
        # for potential_subparser in getattr(
        #     self._subparsers, "_group_actions", []
        # ):
        #     try:
        #         grid_args = next(
        #             iter(potential_subparser.choices.values())
        #         )._grid_args
        #         is_grid_search = is_grid_search or grid_args
        #     except AttributeError:
        #         continue
        # if len(vals) == 1 and not is_grid_search:
        #     warnings.warn("Use")
        #     return vals[0]

        for ns in vals:
            cfg = {}
            if ns.gridparse_config is not None:
                # reverse for priority to originally first configs
                for potential_fn in reversed(
                    getattr(ns, "gridparse_config", [])
                ):
                    if os.path.isfile(potential_fn):
                        cfg = OmegaConf.merge(cfg, OmegaConf.load(potential_fn))

                for arg in cfg:
                    if not hasattr(ns, arg):
                        continue
                    if arg not in ns.___specified_args___:
                        setattr(ns, arg, cfg.get(arg))

            if not self._retain_config_filename:
                delattr(ns, "gridparse_config")

            delattr(ns, "___specified_args___")

        return vals

    def _check_value(self, action, value):
        """Overwrites `_check_value` to support grid search with `None`s."""
        # converted value must be one of the choices (if specified)
        if action.choices is not None and (
            value not in action.choices and value is not None
        ):  # allows value to be None without error
            args = {
                "value": value,
                "choices": ", ".join(map(repr, action.choices)),
            }
            msg = argparse._(
                "invalid choice: %(value)r (choose from %(choices)s)"
            )
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
            # and action.dest in self._grid_args
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

    @staticmethod
    def _add_split_in_arg(arg: str, split: str) -> str:
        """Adds the `split` to the name of the argument `arg`."""

        if "_" in arg:
            # if the user uses "_" as a delimiter, we use that
            delim = "_"
        else:
            # otherwise, we use "-" (no necessary to check for it, e.g., could be CamelCase)
            delim = "-"
        return split + delim + arg

    def add_argument(
        self, *args, **kwargs
    ) -> Union[argparse.Action, List[argparse.Action]]:
        """Augments `add_argument` to support grid search.
        For parameters that are searchable, provide specification
        for a single value, and set the new argument `searchable`
        to `True`.
        """

        ## copy-pasted code
        chars = self.prefix_chars
        if not args or (len(args) == 1 and args[0][0] not in chars):
            if args and "dest" in kwargs:
                raise ValueError("dest supplied twice for positional argument")
            new_kwargs = self._get_positional_kwargs(*args, **kwargs)

        # otherwise, we're adding an optional argument
        else:
            new_kwargs = self._get_optional_kwargs(*args, **kwargs)
        ## edoc detsap-ypoc

        # create multiple arguments for each split
        splits = kwargs.pop("splits", [])
        if splits:
            actions = []
            for split in splits:

                cp_args = deepcopy(list(args))
                cp_kwargs = deepcopy(kwargs)

                if args:
                    i = 0
                    while cp_args[0][i] in self.prefix_chars:
                        i += 1

                    cp_args[0] = cp_args[0][:i] + self._add_split_in_arg(
                        cp_args[0][i:], split
                    )

                else:
                    cp_kwargs["dest"] = self._add_split_in_arg(
                        cp_kwargs["dest"], split
                    )

                actions.append(self.add_argument(*cp_args, **cp_kwargs))

            return actions

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
                type = list_as_delim_str(type, delimiter="|")
            else:
                nargs = "+"

            kwargs["nargs"] = nargs
            kwargs["type"] = type

        # doesn't add `searchable` in _StoreAction
        return super().add_argument(*args, **kwargs)

    class Subspace:
        def __init__(self, parent: Optional["Subspace"] = None):
            self.args = {}
            self.subspaces = {}
            self.cnt = 0
            self.parent = parent

        def add_arg(self, arg: str):
            if arg == "{":
                new_subspace = GridArgumentParser.Subspace(self)
                self.subspaces[self.cnt] = new_subspace
                self.cnt += 1
                return new_subspace
            elif arg == "}":
                return self.parent
            else:
                self.args[self.cnt] = arg
                self.cnt += 1
                return self

        def parse_paths(self) -> List[List[str]]:

            if not self.subspaces:
                return [list(self.args.values())]

            this_subspace_args = []
            cumulative_args = []

            for i in range(self.cnt):
                if i in self.subspaces:
                    paths = self.subspaces[i].parse_paths()
                    for path in paths:
                        cumulative_args.append(this_subspace_args + path)
                else:
                    this_subspace_args.append(self.args[i])
                    for path in cumulative_args:
                        path.append(self.args[i])

            return cumulative_args

        def __repr__(self) -> str:
            repr = "Subspace("
            for i in range(self.cnt):
                if i in self.subspaces:
                    repr += f"{self.subspaces[i]}, "
                else:
                    repr += f"{self.args[i]}, "
            repr = repr[:-2] + ")"
            return repr

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
        root_subspace = self.Subspace()
        current_subspace = root_subspace

        for arg in arg_strings:
            current_subspace = current_subspace.add_arg(arg)

        all_arg_strings = root_subspace.parse_paths()
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
