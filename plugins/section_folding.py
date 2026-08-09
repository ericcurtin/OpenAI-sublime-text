"""OpenAI Completion adapter for shared typed chat sections and folding."""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

import sublime
import sublime_plugin

from .vendor.sublime_chat_ui.folding import SectionRuntime, section_key
from .vendor.sublime_chat_ui.sections import (
    SectionEdit,
    SectionKey,
    SectionMutation,
    SectionMutationKind,
)

logger = logging.getLogger(__name__)

CHAT_VIEW_FLAG = 'openai_is_chat_transcript'
FOLD_SETTINGS_CHANGE_KEY = 'openai-fold-sections'


def _region(begin: int, end: int):
    return sublime.Region(begin, end)


def _views_for_buffer(view) -> list:
    matches = []
    for window in sublime.windows():
        matches.extend(candidate for candidate in window.views() if candidate.buffer_id() == view.buffer_id())
    return matches or [view]


def _apply_edit(view, edit: SectionEdit) -> None:
    was_read_only = bool(view.is_read_only())
    view.set_read_only(False)
    try:
        view.run_command(
            'openai_apply_section_edit',
            {
                'begin': edit.begin,
                'end': edit.end,
                'text': edit.text,
            },
        )
    finally:
        view.set_read_only(was_read_only)


_RUNTIME = SectionRuntime(
    region_factory=_region,
    edit_applier=_apply_edit,
    views_for_buffer=_views_for_buffer,
)


def fold_section_names() -> set[str]:
    raw = sublime.load_settings('openAI.sublime-settings').get('fold_sections', [])
    if not isinstance(raw, list):
        return set()
    return {name.strip().lower() for name in raw if isinstance(name, str) and name.strip()}


def mark_chat_view(view) -> None:
    view.settings().set(CHAT_VIEW_FLAG, True)


def is_chat_view(view) -> bool:
    settings = view.settings()
    if settings.get(CHAT_VIEW_FLAG):
        return True
    try:
        return view.name() == 'AI Chat' or settings.get('sheet_view') == 'AI Chat'
    except RuntimeError:
        return False


@dataclass(frozen=True, slots=True)
class ActiveSection:
    key: SectionKey
    header: str


class OpenAISectionProjection:
    """Map OpenAI's sequential role stream onto shared stable sections."""

    def __init__(self) -> None:
        self._active: dict[int, ActiveSection] = {}
        self._sequence = itertools.count(1)

    def start(self, view, header: str) -> SectionKey:
        mark_chat_view(view)
        self.finalize(view)
        key = section_key(
            f'openai:{view.buffer_id()}',
            next(self._sequence),
        )
        assert key is not None
        self._active[view.buffer_id()] = ActiveSection(key=key, header=header)
        _RUNTIME.apply_mutation(
            view,
            SectionMutation(
                kind=SectionMutationKind.CREATE,
                key=key,
                header=header,
                body='',
            ),
            fold_section_names(),
        )
        return key

    def append(self, view, text: str) -> None:
        if not text:
            return
        active = self._active.get(view.buffer_id())
        if active is None:
            self.start(view, '## Output')
            active = self._active[view.buffer_id()]
        _RUNTIME.apply_mutation(
            view,
            SectionMutation(
                kind=SectionMutationKind.APPEND_DELTA,
                key=active.key,
                header=None,
                body=text,
            ),
            fold_section_names(),
        )

    def finalize(self, view) -> None:
        active = self._active.pop(view.buffer_id(), None)
        if active is None:
            return
        _RUNTIME.apply_mutation(
            view,
            SectionMutation(
                kind=SectionMutationKind.FINALIZE,
                key=active.key,
                header=None,
                body='',
            ),
            fold_section_names(),
        )

    def reset(self, view) -> None:
        self._active.pop(view.buffer_id(), None)
        _RUNTIME.invalidate_view(view)

    def clear(self) -> None:
        self._active.clear()
        _RUNTIME.clear()


SECTION_PROJECTION = OpenAISectionProjection()


def restore_folds(view) -> None:
    mark_chat_view(view)
    _RUNTIME.restore(view, fold_section_names())


def sync_folds(view) -> None:
    _RUNTIME.sync(view, fold_section_names())


def sync_all_chat_views() -> None:
    for window in sublime.windows():
        for view in window.views():
            if is_chat_view(view):
                mark_chat_view(view)
                sync_folds(view)
        panel = window.find_output_panel('AI Chat')
        if panel is not None:
            mark_chat_view(panel)
            sync_folds(panel)


class OpenaiApplySectionEditCommand(sublime_plugin.TextCommand):
    def run(self, edit, begin: int, end: int, text: str) -> None:
        if begin < 0 or end < begin or end > self.view.size():
            raise ValueError(f'Invalid chat section edit region: {begin}:{end}')
        self.view.replace(edit, sublime.Region(begin, end), text)


class OpenaiSectionFoldingListener(sublime_plugin.EventListener):
    def on_activated(self, view) -> None:
        if is_chat_view(view):
            restore_folds(view)

    def on_post_text_command(self, view, command_name: str, args: dict | None) -> None:
        del command_name, args
        if is_chat_view(view):
            _RUNTIME.reconcile(view)

    def on_reload(self, view) -> None:
        if not is_chat_view(view):
            return
        _RUNTIME.invalidate_view(view)
        restore_folds(view)

    def on_revert(self, view) -> None:
        self.on_reload(view)

    def on_pre_close(self, view) -> None:
        if not is_chat_view(view):
            return
        _RUNTIME.reconcile(view)
        _RUNTIME.forget_view(view)


def plugin_loaded() -> None:
    settings = sublime.load_settings('openAI.sublime-settings')
    settings.clear_on_change(FOLD_SETTINGS_CHANGE_KEY)
    settings.add_on_change(FOLD_SETTINGS_CHANGE_KEY, sync_all_chat_views)
    sublime.set_timeout(sync_all_chat_views, 0)


def plugin_unloaded() -> None:
    sublime.load_settings('openAI.sublime-settings').clear_on_change(FOLD_SETTINGS_CHANGE_KEY)
    SECTION_PROJECTION.clear()


__all__ = [
    'CHAT_VIEW_FLAG',
    'SECTION_PROJECTION',
    'OpenaiApplySectionEditCommand',
    'OpenaiSectionFoldingListener',
    'mark_chat_view',
    'plugin_loaded',
    'plugin_unloaded',
    'restore_folds',
    'sync_all_chat_views',
    'sync_folds',
]
