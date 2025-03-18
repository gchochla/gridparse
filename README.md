# GridParse

A lightweight (only dependency is `omegaconf` which also downloads `yaml`) `ArgumentParser` --- aka `GridArgumentParser` --- that supports your *grid-search* needs. Supports top-level parser and subparsers. Configuration files of any type (using `omegaconf`) as also support through the argument `--gridparse-config` (also available with underscore `_`), where multiple configuration files can be passed and parsed.

## Overview

It transforms the following arguments in the corresponding way:

`--arg 1` &rarr; `--arg 1 2 3`

`--arg 1 2 3` &rarr; `--arg 1~~2~~3 4~~5~~6`

`--arg 1-2-3 4-5-6` &rarr; `--arg 1-2-3~~4-5-6 7-8-9~~10-11`

So, for single arguments, it extends them similar to nargs="+". For multiple arguments, it extends them with `list_as_dashed_str(type, delimiter="~~")` (available in `gridparse.utils`), and this is recursively applied with existing `list_as_dashed_str` types. It can also handle subspaces using square brackets, where you can enclose combinations of hyperparameters within but don't have them combine with values of hyperparameters in other subspaces of the same length.

*Note*: when using at least on searchable argument, the return value of `parse_args()` is always a list of Namespaces, otherwise it is just a Namespace.

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

## Additional capabilities

### Configuration files

Using `omegaconf` (the only dependency), we allow users to specify (potentially multiple) configuration files that can be used to populate the resulting namespace(s). Access the through the `gridparse-config` argument: `--gridparse-config /this/config.json /that/config.yml`. Command-line arguments are given higher priority, and then the priority is in order of appearance in the command line for the configuration files.

### Specify `None` in command-line

In case some parameter is searchable (and not a boolean), you might need one of the values to be the default value `None`. In that case, specifying any other value would rule the value `None` out from the grid search. To avoid this, `gridparse` allows you to specify the value `_None_` in the command line:

```python
>>> parser = gridparse.GridArgumentParser()
>>> parser.add_argument('--text', type=str, searchable=True)
>>> parser.parse_args("--text a b _None_".split())
[Namespace(text='a'), Namespace(text='b'), Namespace(text=None)]
```

### Access values of other parameter

Moreover, you can use the value (not the default) of another argument as the default by setting the default to `args.<name-of-other-argument>`.

```python
>>> parser = gridparse.GridArgumentParser()
>>> parser.add_argument('--num', type=int, searchable=True)
>>> parser.add_argument('--other-num', type=int, searchable=True, default="args.num")
>>> parser.parse_args("--num 1 2".split())
[Namespace(num=1, other_num=1), Namespace(num=2, other_num=2)]
```

You can also specify so in the command line, i.e., `args.<name-of-other-argument>` does not have to appear in the default value of the argument.

This allows you the flexibility to have a parameter default to another parameter's values, and then specify different values when need arises (example use case: specify different CUDA device for a specific component only when OOM errors are encountered, and have it default to the "general" device otherwise).

### Different value for each dataset split

You can specify the kw argument `splits` to create one argument per split:

```python
>>> parser = gridparse.GridArgumentParser()
>>> parser.add_argument('--num', type=int, searchable=True)
>>> parser.add_argument('--other-num', type=int, splits=["train", "test"])
>>> parser.parse_args("--num 1 2 --train-other-num 3 --test-other-num 5".split())
[Namespace(num=1, test_other_num=5, train_other_num=3), Namespace(num=2, test_other_num=5, train_other_num=3)]
```

Note that if an underscore (`_`) exists in the name of the argument, the new names will also join the splits with the original name with an underscore: `--other_num` to `--train_other_num`, etc. The new arguments are separate, i.e. if searchable, you do *not* have to specify the same number of values, etc. They each gain all the properties specified in the original argument.
