# GridParse

A lightweight (no dependencies) `ArgumentParser` --- aka `GridArgumentParser` --- that supports your *grid-search* needs. Supports top-level parser and subparsers.

## Overview

It transforms the following arguments in the corresponding way:

`--arg 1` &rarr; `--arg 1 2 3`

`--arg 1 2 3` &rarr; `--arg 1~~2~~3 4~~5~~6`

`--arg 1-2-3 4-5-6` &rarr; `--arg 1-2-3~~4-5-6 7-8-9~~10-11`

So, for single arguments, it extends them similar to nargs="+". For multiple arguments, it extends them with `list_as_dashed_str(type, delimiter="~~")` (available in `gridparse.utils`), and this is recursively applied with existing `list_as_dashed_str` types. It can also handle subspaces using square brackets, where you can enclose combinations of hyperparameters within but don't have them combine with values of hyperparameters in other subspaces of the same length.

## Examples

Example without subspaces:

```python
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

```python
[
    
Namespace(hparam1=[1, 2, 3], hparam2=[4, 3], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),

Namespace(hparam1=[1, 2, 3], hparam2=[5, 4], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),

Namespace(hparam1=[1, 2, 3], hparam2=[6, 5], lists=[['1', '2', '3']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),

Namespace(hparam1=[1, 2, 3], hparam2=[4, 3], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),

Namespace(hparam1=[1, 2, 3], hparam2=[5, 4], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']]),

Namespace(hparam1=[1, 2, 3], hparam2=[6, 5], lists=[['3', '4', '5'], ['6', '7']], normal='efrgthytfgn', normal_lists=[['1', '2', '3'], ['4', '5', '6']])

]
```

Example with subspaces:

```python
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