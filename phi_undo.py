# -*- coding: utf-8 -*-
"""撤销 / 重做栈。

用法：每次修改**前**调用 push(label, snapshot)，撤销时用当前快照换回上一个快照。
"""

import copy


class UndoStack:
    def __init__(self, limit=60):
        self.limit = limit
        self.undo_stack = []   # [(label, snapshot)]
        self.redo_stack = []   # [(label, snapshot)]

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()

    def push(self, label, snapshot):
        """修改前调用：记录修改前的状态"""
        self.undo_stack.append((label, copy.deepcopy(snapshot)))
        self.redo_stack.clear()
        while len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def next_undo_label(self):
        return self.undo_stack[-1][0] if self.undo_stack else ""

    def next_redo_label(self):
        return self.redo_stack[-1][0] if self.redo_stack else ""

    def undo(self, current_snapshot):
        """返回应恢复到的快照；无历史则返回 None"""
        if not self.undo_stack:
            return None
        label, snap = self.undo_stack.pop()
        self.redo_stack.append((label, copy.deepcopy(current_snapshot)))
        return snap

    def redo(self, current_snapshot):
        if not self.redo_stack:
            return None
        label, snap = self.redo_stack.pop()
        self.undo_stack.append((label, copy.deepcopy(current_snapshot)))
        return snap
