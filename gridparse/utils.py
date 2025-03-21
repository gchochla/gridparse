import argparse
from typing import Callable


# NOTE: has issues with negative numbers if delim="-"
def list_as_delim_str(actual_type: Callable, delimiter: str = ","):
    """Creates a function that converts a string to a list of elements.

    Can be used as the `type` argument in `argparse` to convert
    a string to a list of elements, e.g.: `["1,2,3", "4,5,6"]` to
    `[[1, 2, 3], [4, 5, 6]]` (note that this operates on a single
    `str` at a time, use `nargs` to pass multiple).

    Args:
        actual_type: the type of the elements in the list
            (or any function that takes a `str` and returns something).
        delimiter: the delimiter between elements in `str`.
    """

    def _list_of_lists(s: str):
        if s == "None":
            return None
        l = [actual_type(e) for e in s.split(delimiter)]
        return l

    return _list_of_lists


def strbool(arg: str):
    """Converts a string boolean to an actual boolean.

    This is useful for searching over boolean hyperparameters,
    because now multiple values can be passed with `searchable=True`:
    "--flag true false".

    Args:
        arg: the string to convert.

    Raises:
        argparse.ArgumentTypeError: if the string is not a valid boolean.
    """
    if isinstance(arg, bool):
        return arg

    if arg is None:
        return False

    if arg.lower() == 'true':
        return True
    if arg.lower() == 'false':
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')
