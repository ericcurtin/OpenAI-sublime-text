from __future__ import annotations

import importlib
import sys
import types
import unittest


class FakeRegion:
    def __init__(self, begin, end=None):
        self._begin = begin
        self._end = begin if end is None else end

    def begin(self):
        return self._begin

    def end(self):
        return self._end

    def __eq__(self, other):
        return isinstance(other, FakeRegion) and (self.begin(), self.end()) == (
            other.begin(),
            other.end(),
        )


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.callbacks = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def add_on_change(self, key, callback):
        self.callbacks[key] = callback

    def clear_on_change(self, key):
        self.callbacks.pop(key, None)


class FakeView:
    _next_id = 1

    def __init__(self, window):
        self.text = ''
        self.folded = []
        self._window = window
        self._settings = FakeSettings()
        self._read_only = True
        self._id = FakeView._next_id
        FakeView._next_id += 1

    def id(self):
        return self._id

    def buffer_id(self):
        return self._id

    def window(self):
        return self._window

    def settings(self):
        return self._settings

    def size(self):
        return len(self.text)

    def substr(self, value):
        if isinstance(value, int):
            return self.text[value]
        return self.text[value.begin() : value.end()]

    def is_read_only(self):
        return self._read_only

    def set_read_only(self, value):
        self._read_only = value

    def run_command(self, command, args):
        if command != 'openai_apply_section_edit':
            raise AssertionError(command)
        self.text = self.text[: args['begin']] + args['text'] + self.text[args['end'] :]

    def fold(self, region):
        if region not in self.folded:
            self.folded.append(region)

    def unfold(self, region):
        self.folded = [candidate for candidate in self.folded if candidate != region]

    def is_folded(self, region):
        return region in self.folded

    def replace(self, edit, region, text):
        del edit
        self.text = self.text[: region.begin()] + text + self.text[region.end() :]


class FakeWindow:
    def __init__(self):
        self._views = []
        self.panel = None

    def views(self):
        return self._views

    def find_output_panel(self, name):
        return self.panel if name == 'AI Chat' else None


def load_section_folding_module():
    original_sublime = sys.modules.get('sublime')
    original_plugin = sys.modules.get('sublime_plugin')
    settings = FakeSettings({'fold_sections': ['Answer']})
    windows = []

    sublime = types.ModuleType('sublime')
    sublime.Region = FakeRegion
    sublime.windows = lambda: windows
    sublime.load_settings = lambda name: settings
    sublime.set_timeout = lambda callback, delay=0: callback()

    sublime_plugin = types.ModuleType('sublime_plugin')
    sublime_plugin.EventListener = object
    sublime_plugin.TextCommand = object

    try:
        sys.modules['sublime'] = sublime
        sys.modules['sublime_plugin'] = sublime_plugin
        sys.modules.pop('plugins.section_folding', None)
        module = importlib.import_module('plugins.section_folding')
    finally:
        if original_sublime is None:
            sys.modules.pop('sublime', None)
        else:
            sys.modules['sublime'] = original_sublime
        if original_plugin is None:
            sys.modules.pop('sublime_plugin', None)
        else:
            sys.modules['sublime_plugin'] = original_plugin
    return module, settings, windows


section_folding, fold_settings, sublime_windows = load_section_folding_module()


class OpenAISectionProjectionTests(unittest.TestCase):
    def setUp(self):
        section_folding.SECTION_PROJECTION.clear()
        fold_settings.values['fold_sections'] = ['Answer']
        self.window = FakeWindow()
        self.view = FakeView(self.window)
        self.window._views.append(self.view)
        self.window.panel = self.view
        sublime_windows[:] = [self.window]

    def test_streaming_answer_uses_one_typed_section_and_exact_fold(self):
        projection = section_folding.SECTION_PROJECTION

        projection.start(self.view, '## Answer\n\n')
        projection.append(self.view, 'first ')
        projection.append(self.view, 'second')

        self.assertEqual(self.view.text.count('----------'), 1)
        self.assertEqual(self.view.text.count('## Answer'), 1)
        self.assertIn('first second', self.view.text)
        self.assertEqual(len(self.view.folded), 1)
        self.assertNotIn('----------', self.view.substr(self.view.folded[0]))

    def test_next_role_finalizes_previous_section_and_starts_another(self):
        projection = section_folding.SECTION_PROJECTION
        projection.start(self.view, '## Answer')
        projection.append(self.view, 'done')
        projection.start(self.view, '## Question')
        projection.append(self.view, 'next')

        self.assertEqual(self.view.text.count('----------'), 2)
        self.assertLess(self.view.text.index('## Answer'), self.view.text.index('## Question'))
        self.assertIn('next', self.view.text)

    def test_settings_sync_unfolds_removed_section(self):
        projection = section_folding.SECTION_PROJECTION
        projection.start(self.view, '## Answer')
        projection.append(self.view, 'done')
        self.assertEqual(len(self.view.folded), 1)

        fold_settings.values['fold_sections'] = []
        section_folding.sync_all_chat_views()

        self.assertEqual(self.view.folded, [])


if __name__ == '__main__':
    unittest.main()
