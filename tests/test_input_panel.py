import importlib
import sys
import types
import unittest


class FakeRegion:
    def __init__(self, a, b=None):
        self.a = a
        self.b = a if b is None else b

    def begin(self):
        return min(self.a, self.b)

    def end(self):
        return max(self.a, self.b)

    def empty(self):
        return self.a == self.b


class FakeSettings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def erase(self, key):
        self.values.pop(key, None)


class FakeSelection(list):
    def add(self, region):
        self.append(region)


class FakeWindow:
    def __init__(self, window_id=1):
        self.window_id = window_id
        self.window_settings = FakeSettings()
        self.panel = None
        self.commands = []

    def id(self):
        return self.window_id

    def settings(self):
        return self.window_settings

    def find_output_panel(self, name):
        return self.panel

    def active_panel(self):
        return 'output.openai_input' if self.panel is not None else None

    def run_command(self, command, args=None):
        self.commands.append((command, args))


class FakePanel:
    def __init__(self, window, text='', caret=0, panel_id=7):
        self._window = window
        self.text = text
        self.caret = caret
        self.panel_id = panel_id
        self.selection = FakeSelection([FakeRegion(caret)])
        window.panel = self

    def id(self):
        return self.panel_id

    def window(self):
        return self._window

    def size(self):
        return len(self.text)

    def substr(self, region):
        return self.text[region.begin() : region.end()]

    def sel(self):
        return self.selection

    def rowcol(self, point):
        prefix = self.text[:point]
        row = prefix.count('\n')
        column = len(prefix.rsplit('\n', 1)[-1])
        return row, column


def load_input_panel_module():
    module_names = ('sublime', 'sublime_plugin', 'llm_runner')
    original_modules = {name: sys.modules.get(name) for name in module_names}

    sublime = types.ModuleType('sublime')
    sublime.Region = FakeRegion
    sublime.View = object
    sublime.Window = object
    sublime.status_message = lambda message: None
    sublime.get_clipboard = lambda: ''

    sublime_plugin = types.ModuleType('sublime_plugin')
    sublime_plugin.EventListener = object
    sublime_plugin.TextCommand = object
    sublime_plugin.WindowCommand = object

    llm_runner = types.ModuleType('llm_runner')
    llm_runner.AssistantSettings = object
    llm_runner.SublimeInputContent = object

    try:
        sys.modules['sublime'] = sublime
        sys.modules['sublime_plugin'] = sublime_plugin
        sys.modules['llm_runner'] = llm_runner
        sys.modules.pop('plugins.input_panel', None)
        return importlib.import_module('plugins.input_panel')
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


input_panel = load_input_panel_module()


class PromptHistorySessionTests(unittest.TestCase):
    def test_previous_starts_at_latest_and_preserves_draft(self):
        session = input_panel.PromptHistorySession()

        self.assertEqual(session.previous(['one', 'two'], 'draft'), 'two')
        self.assertEqual(session.previous(['one', 'two'], 'ignored'), 'one')
        self.assertEqual(session.previous(['one', 'two'], 'ignored'), 'one')
        self.assertTrue(session.browsing)

    def test_next_returns_to_draft_and_leaves_history_mode(self):
        session = input_panel.PromptHistorySession()
        session.previous(['one', 'two'], 'draft')
        session.previous(['one', 'two'], 'ignored')

        self.assertEqual(session.next(['one', 'two']), 'two')
        self.assertEqual(session.next(['one', 'two']), 'draft')
        self.assertFalse(session.browsing)
        self.assertIsNone(session.next(['one', 'two']))

    def test_empty_history_does_not_enter_history_mode(self):
        session = input_panel.PromptHistorySession()

        self.assertIsNone(session.previous([], 'draft'))
        self.assertFalse(session.browsing)


class InputPanelControllerTests(unittest.TestCase):
    def setUp(self):
        input_panel.OpenAIInputPanelController._pending_requests.clear()
        input_panel.OpenAIInputPanelController._history_sessions.clear()
        self.window = FakeWindow()

    def test_draft_round_trip_and_clear(self):
        controller = input_panel.OpenAIInputPanelController

        controller.save_draft(self.window, 'unfinished')
        self.assertEqual(controller.get_draft(self.window), 'unfinished')
        controller.clear_draft(self.window)
        self.assertEqual(controller.get_draft(self.window), '')

    def test_history_keeps_all_submitted_prompts_in_order(self):
        controller = input_panel.OpenAIInputPanelController

        for prompt in ['one', 'one', 'two']:
            controller.record_history(self.window, prompt)

        self.assertEqual(controller.get_history(self.window), ['one', 'one', 'two'])

    def test_history_ignores_malformed_storage(self):
        controller = input_panel.OpenAIInputPanelController
        self.window.settings().set(controller.HISTORY_STORAGE_KEY, ['ok', 3, '', None])

        self.assertEqual(controller.get_history(self.window), ['ok'])

    def test_navigation_requires_first_row_first_column(self):
        controller = input_panel.OpenAIInputPanelController
        controller.record_history(self.window, 'old prompt')

        panel = FakePanel(self.window, 'draft', caret=0)
        self.assertTrue(controller.should_navigate_previous(panel))

        panel.selection[:] = [FakeRegion(1)]
        self.assertFalse(controller.should_navigate_previous(panel))

        panel.selection[:] = [FakeRegion(0, 1)]
        self.assertFalse(controller.should_navigate_previous(panel))

    def test_cancel_saves_draft_clears_pending_and_hides_panel(self):
        controller = input_panel.OpenAIInputPanelController
        FakePanel(self.window, 'unfinished', caret=10)
        controller._pending_requests[self.window.id()] = object()

        controller.cancel(self.window)

        self.assertEqual(controller.get_draft(self.window), 'unfinished')
        self.assertIsNone(controller.get_pending_request(self.window))
        self.assertEqual(self.window.commands[-1], ('hide_panel', None))


class InputPanelEventListenerTests(unittest.TestCase):
    def setUp(self):
        input_panel.OpenAIInputPanelController._history_sessions.clear()
        input_panel.OpenAIInputPanelController._pending_requests.clear()
        input_panel.OpenAIInputPanelController._hiding_windows.clear()
        self.window = FakeWindow()
        self.panel = FakePanel(self.window, 'draft', caret=0)
        self.listener = input_panel.OpenaiInputPanelEventListener()

    def test_paste_is_replaced_with_code_block_command(self):
        self.assertEqual(
            self.listener.on_text_command(self.panel, 'paste_and_indent', None),
            ('openai_paste_as_code_block', None),
        )

    def test_generic_hide_panel_is_redirected_to_draft_saving_cancel(self):
        input_panel.OpenAIInputPanelController._pending_requests[self.window.id()] = object()

        self.assertEqual(
            self.listener.on_window_command(self.window, 'hide_panel', None),
            ('openai_cancel_input_panel', None),
        )

        input_panel.OpenAIInputPanelController._hiding_windows.add(self.window.id())
        self.assertIsNone(self.listener.on_window_command(self.window, 'hide_panel', None))

    def test_up_enters_history_and_down_only_intercepts_while_browsing(self):
        controller = input_panel.OpenAIInputPanelController
        controller.record_history(self.window, 'old prompt')

        self.assertEqual(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': False},
            ),
            ('openai_input_history_previous', None),
        )
        self.assertIsNone(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': True},
            )
        )

        controller.history_session(self.window).previous(['old prompt'], 'draft')
        self.assertEqual(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': True},
            ),
            ('openai_input_history_next', None),
        )


if __name__ == '__main__':
    unittest.main()
