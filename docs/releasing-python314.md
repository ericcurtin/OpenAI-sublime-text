# Python 3.14 release coordination

The release line after 6.1.0 targets Sublime Text build 4205 or newer and its
Python 3.14 plugin host. Package Control cannot express a library version
specifier in `dependencies.json`; entries are library names selected for the
package's active Python runtime. Compatibility therefore depends on coordinated
package and library channel metadata.

## Package tags

- Keep historical, unprefixed package tags unchanged. The latest compatible one
  for Sublime Text 4050–4204 is `6.1.0`.
- Tag every Python 3.14 package release as `py314-X.Y.Z`, for example
  `py314-6.2.0`.
- The default Package Control channel keeps unprefixed tags as a fallback for
  builds 4050 and newer, while `py314-` tags are visible only to builds 4205
  and newer. Once `py314-6.2.0` exists, its higher version wins on new builds;
  old builds remain on unprefixed `6.1.0`.

## Coordinated release order

1. Merge the `llm_runner` Linux ARM64 channel fix. Each floating template lists
   Python 3.8, 3.13, and 3.14; Package Control independently selects the newest
   compatible wheel for each runtime.
2. Publish `llm_runner` 0.3.0 with only CPython 3.14 wheels and
   `requires-python >=3.14`.
3. Wait for the library-channel crawler and verify all supported platforms
   resolve 0.3.0 for Python 3.14, while Python 3.8 and 3.13 continue resolving
   their latest compatible legacy wheels.
4. Merge the package-channel `py314-` release source. Its overlapping legacy
   source keeps 6.1.0 installable until the new tag exists.
5. Tag the selected plugin release commit as `py314-6.2.0` and verify the
   default channel exposes it only to Sublime Text 4205 and newer.

Do not publish step 5 until the Python 3.14 library artifacts and library
channel change are live. An already-installed 6.1.0 package on a Sublime
upgrade to 4205 is interpreted by the new host as Python 3.14, so the 0.3.x
library must remain API-compatible with 6.1.0 during the transition. Package
Control offers no per-package library version pin that can remove this
transition case.
