# Python 3.14 release coordination

The release line after 6.0.0 targets Sublime Text build 4205 or newer and its
Python 3.14 plugin host. Package Control cannot express a library version
specifier in `dependencies.json`; entries are library names selected for the
package's active Python runtime. Compatibility therefore depends on coordinated
package and library channel metadata.

## Package tags

- Keep historical, unprefixed package tags unchanged. The latest compatible one
  for Sublime Text 4050–4204 is `6.0.0`.
- Tag every Python 3.14 package release as `py314-X.Y.Z`, for example
  `py314-6.1.0`.
- The default Package Control channel maps unprefixed tags to builds 4050–4204
  and `py314-` tags to builds 4205 and newer.

## Coordinated release order

1. Merge the `llm_runner` library-channel split. Its Python 3.8 and 3.13 wheel
   templates stay fixed at PyPI version 0.2.14; Python 3.14 uses the future line.
2. Merge the package-channel tag/build split.
3. Publish `llm_runner` 0.3.0 wheels for every supported platform and verify
   the Package Control crawler resolves them for Python 3.14 only.
4. Tag the plugin with the `py314-` prefix.

Do not publish step 4 until the Python 3.14 library artifacts and both channel
changes are live. An already-installed 6.0.0 package on a Sublime upgrade to
4205 is interpreted by the new host as Python 3.14, so the 0.3.x library must
remain API-compatible with 6.0.0 during the transition. Package Control offers
no per-package library version pin that can remove this transition case.
