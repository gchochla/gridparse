# Changelog

All notable changes to this project will be documented in this file.

## [1.5.3] - 2025-03-20

## Fixed
- Bug with negative numbers in lists as strs

## Changes
- Delimiter of `nargs` of searchable argument from `~~` to `|`
- Util name form `list_as_dashed_str` to `list_as_delim_str`
- Default delimiter in (now) `list_as_delim_str` changed to `,` (avoids errors with negative numbers)

## [1.5.2] - 2025-03-19

### Fixed
- Bug caused by leftover code

## [1.5.1] - 2025-03-18

### Fixed
- Bug where config file would not override unspecified arguments that had a default value.

## [1.5.0] - 2025-03-17

### Added
- Ability to use configuration files (of any kind with `omegaconf`) to populate the returned namespaces.