from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, List

import sublime
from llm_runner import AssistantSettings, SublimeInputContent  # type: ignore
from sublime import Region, View, Window
from sublime_plugin import EventListener, TextCommand, WindowCommand

logger = logging.getLogger(__name__)


@dataclass
class PendingInputRequest:
    source_view: View
    assistant: AssistantSettings | None
    inputs: List[SublimeInputContent]


class OpenAIInputPanelController:
    PANEL_NAME = 'openai_input'
    _pending_requests: Dict[int, PendingInputRequest] = {}

    @classmethod
    def is_input_panel_view(cls, view: View | None) -> bool:
        if view is None:
            return False
        window = view.window()
        if window is None:
            return False
        panel = window.find_output_panel(cls.PANEL_NAME)
        return panel is not None and panel.id() == view.id()

    @staticmethod
    def _replace_panel_content(panel: View, text: str) -> None:
        panel.run_command('select_all')
        panel.run_command('right_delete')
        if text:
            panel.run_command('append', {'characters': text, 'force': True})

    @classmethod
    def show(
        cls,
        window: Window,
        source_view: View,
        assistant: AssistantSettings | None,
        inputs: List[SublimeInputContent],
    ) -> None:
        cls._pending_requests[window.id()] = PendingInputRequest(
            source_view=source_view,
            assistant=assistant,
            inputs=inputs,
        )

        panel = window.create_output_panel(cls.PANEL_NAME)
        panel.set_read_only(False)
        panel.assign_syntax('Packages/Markdown/MultiMarkdown.sublime-syntax')
        panel.settings().set('scroll_past_end', True)
        panel.settings().set('gutter', True)
        panel.settings().set('line_numbers', False)
        panel.settings().set('fold_buttons', False)
        panel.settings().set('word_wrap', True)
        cls._replace_panel_content(panel, '')

        panel.sel().clear()
        panel.sel().add(Region(panel.size()))

        window.run_command('show_panel', {'panel': f'output.{cls.PANEL_NAME}'})
        window.focus_view(panel)
        panel.show(panel.size())

    @classmethod
    def get_pending_request(cls, window: Window) -> PendingInputRequest | None:
        return cls._pending_requests.get(window.id())

    @classmethod
    def clear_pending_request(cls, window: Window) -> None:
        cls._pending_requests.pop(window.id(), None)


class OpenaiSubmitInputPanelCommand(WindowCommand):
    def run(self) -> None:
        panel_view = self.window.find_output_panel(OpenAIInputPanelController.PANEL_NAME)
        if panel_view is None:
            sublime.status_message('OpenAI input panel is not open')
            return

        pending_request = OpenAIInputPanelController.get_pending_request(self.window)
        if pending_request is None:
            sublime.status_message('OpenAI input request is missing')
            return

        prompt = panel_view.substr(Region(0, panel_view.size())).strip()
        if not prompt:
            sublime.status_message('Prompt is empty')
            return

        if pending_request.assistant is None:
            sublime.status_message('Assistant settings are unavailable')
            return

        from .openai_base import CommonMethods

        CommonMethods.save_input(prompt, self.window)
        OpenAIInputPanelController.clear_pending_request(self.window)
        self.window.run_command('hide_panel')
        CommonMethods.handle_input(
            prompt,
            pending_request.source_view,
            pending_request.assistant,
            pending_request.inputs,
        )


class OpenaiSubmitInputPanelFromViewCommand(TextCommand):
    def run(self, edit) -> None:
        window = self.view.window()
        if window is None:
            sublime.status_message('OpenAI input panel window is unavailable')
            return
        window.run_command('openai_submit_input_panel')


class OpenaiPasteAsCodeBlockCommand(TextCommand):
    def run(self, edit) -> None:
        clipboard = sublime.get_clipboard()
        if not clipboard:
            return

        block = f"```\n{clipboard.rstrip(chr(10))}\n```\n\n"
        selections = list(self.view.sel())

        if not selections:
            self.view.insert(edit, self.view.size(), block)
            return

        for region in reversed(selections):
            self.view.replace(edit, region, block)


class OpenaiInputPanelEventListener(EventListener):
    def on_text_command(self, view: View, command_name: str, args):
        if not OpenAIInputPanelController.is_input_panel_view(view):
            return None

        if command_name in {'paste', 'paste_and_indent'}:
            return ('openai_paste_as_code_block', None)

        return None
