from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.deduplication import DuplicateDecision, PossibleDuplicate
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.theme import COLORS, set_button_icon


def _amount_text(amount: Decimal) -> str:
    value = Decimal(amount)
    sign = "-" if value < 0 else "+"
    return f"{sign}${abs(value):,.2f}"


class _DuplicateCard(QFrame):
    def __init__(self, candidate: PossibleDuplicate, changed, parent=None):
        super().__init__(parent)
        self.candidate = candidate
        self._changed = changed
        self.setObjectName("duplicateReviewCard")
        self.setProperty("decision", candidate.decision.value)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.comparison_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.comparison_layout.setSpacing(12)
        existing = candidate.existing_matches[0] if candidate.existing_matches else None
        if existing is None:
            existing_lines = (
                "Earlier occurrence in this import batch",
                candidate.incoming.transaction_date.strftime("%b %d, %Y"),
                candidate.incoming.description,
                _amount_text(candidate.incoming.amount),
                candidate.incoming.account_name,
            )
        else:
            imported = existing.imported_at.strftime("%b %d, %Y %I:%M %p")
            origin = existing.source_file or "Manual transaction"
            existing_lines = (
                existing.transaction_date.strftime("%b %d, %Y"),
                existing.description,
                _amount_text(existing.amount),
                existing.account_name,
                f"Imported: {imported}",
                f"From: {origin}",
            )
        self.comparison_layout.addWidget(
            self._details_panel("EXISTING TRANSACTION", existing_lines)
        )

        incoming_lines = [
            candidate.incoming.transaction_date.strftime("%b %d, %Y"),
            candidate.incoming.description,
            _amount_text(candidate.incoming.amount),
            candidate.incoming.account_name,
            f"From: {candidate.incoming.source_file}",
        ]
        if candidate.incoming.source_transaction_id:
            incoming_lines.append(
                f"Source ID: {candidate.incoming.source_transaction_id}"
            )
        self.comparison_layout.addWidget(
            self._details_panel("INCOMING TRANSACTION", tuple(incoming_lines))
        )
        layout.addLayout(self.comparison_layout)

        reason = QLabel(f"Possible duplicate because: {candidate.reason}")
        reason.setObjectName("duplicateReason")
        reason.setWordWrap(True)
        layout.addWidget(reason)

        actions = QHBoxLayout()
        actions.addStretch()
        self.keep_button = QPushButton("Keep Incoming")
        self.keep_button.setObjectName("duplicateKeepButton")
        set_button_icon(
            self.keep_button,
            "fa6s.check",
            color=COLORS["positive"],
            active_color="#ffffff",
            size=14,
        )
        self.skip_button = QPushButton("Skip Incoming")
        self.skip_button.setObjectName("duplicateSkipButton")
        set_button_icon(
            self.skip_button,
            "fa6s.ban",
            color="#ff9da0",
            active_color="#ffffff",
            size=14,
        )
        self.keep_button.clicked.connect(
            lambda: self.set_decision(DuplicateDecision.KEEP)
        )
        self.skip_button.clicked.connect(
            lambda: self.set_decision(DuplicateDecision.SKIP)
        )
        actions.addWidget(self.keep_button)
        actions.addWidget(self.skip_button)
        layout.addLayout(actions)
        self._refresh()

    @staticmethod
    def _details_panel(title: str, lines: tuple[str, ...]) -> QFrame:
        panel = QFrame()
        panel.setObjectName("duplicateDetailsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("duplicateDetailsTitle")
        panel_layout.addWidget(heading)
        for index, text in enumerate(lines):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setObjectName(
                "duplicateAmount" if index == 2 else "duplicateDetailsText"
            )
            panel_layout.addWidget(label)
        panel_layout.addStretch()
        return panel

    def set_decision(self, decision: DuplicateDecision) -> None:
        self.candidate.decision = decision
        self._refresh()
        self._changed()

    def _refresh(self) -> None:
        self.setProperty("decision", self.candidate.decision.value)
        self.keep_button.setProperty(
            "selected", self.candidate.decision == DuplicateDecision.KEEP
        )
        self.skip_button.setProperty(
            "selected", self.candidate.decision == DuplicateDecision.SKIP
        )
        for widget in (self, self.keep_button, self.skip_button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_narrow(self, narrow: bool) -> None:
        self.comparison_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if narrow
            else QBoxLayout.Direction.LeftToRight
        )


class DuplicateReviewDialog(GenericDialog):
    def __init__(self, candidates: list[PossibleDuplicate], parent=None):
        self.candidates = candidates
        self.cards: list[_DuplicateCard] = []

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        batch_actions = QHBoxLayout()
        self.count_label = QLabel(f"{len(candidates)} possible duplicates")
        self.count_label.setObjectName("duplicateCount")
        batch_actions.addWidget(self.count_label)
        batch_actions.addStretch()
        self.keep_all_button = QPushButton("Keep All")
        self.skip_all_button = QPushButton("Skip All")
        self.reset_button = QPushButton("Reset Decisions")
        self.keep_all_button.setObjectName("duplicateKeepButton")
        self.skip_all_button.setObjectName("duplicateSkipButton")
        self.reset_button.setObjectName("secondaryActionButton")
        set_button_icon(
            self.keep_all_button, "fa6s.check-double",
            color=COLORS["positive"], active_color="#ffffff", size=14,
        )
        set_button_icon(
            self.skip_all_button, "fa6s.ban",
            color="#ff9da0", active_color="#ffffff", size=14,
        )
        set_button_icon(
            self.reset_button, "fa6s.rotate-left",
            color=COLORS["text_muted"], active_color="#ffffff", size=14,
        )
        batch_actions.addWidget(self.keep_all_button)
        batch_actions.addWidget(self.skip_all_button)
        batch_actions.addWidget(self.reset_button)
        content_layout.addLayout(batch_actions)

        scroll = QScrollArea()
        scroll.setObjectName("duplicateReviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        cards_layout = QVBoxLayout(container)
        cards_layout.setContentsMargins(0, 0, 6, 0)
        cards_layout.setSpacing(12)
        for candidate in candidates:
            card = _DuplicateCard(candidate, self._decisions_changed)
            self.cards.append(card)
            cards_layout.addWidget(card)
        cards_layout.addStretch()
        scroll.setWidget(container)
        content_layout.addWidget(scroll, 1)

        super().__init__(
            "Review Possible Duplicates",
            content,
            parent,
            submit_label="Import Selected",
            subtitle="Some transactions may already exist. Review them before importing.",
            icon_name="fa6s.code-compare",
        )
        self.resize(1040, 760)
        self.setMinimumSize(680, 520)
        self.cancel_button.setText("Cancel Import")
        set_button_icon(
            self.cancel_button, "fa6s.xmark",
            color=COLORS["text_muted"], active_color="#ffffff", size=14,
        )
        self.keep_all_button.clicked.connect(
            lambda: self._set_all(DuplicateDecision.KEEP)
        )
        self.skip_all_button.clicked.connect(
            lambda: self._set_all(DuplicateDecision.SKIP)
        )
        self.reset_button.clicked.connect(
            lambda: self._set_all(DuplicateDecision.UNRESOLVED)
        )
        self.submitted.connect(self._accept_if_resolved)
        self._decisions_changed()

    def _set_all(self, decision: DuplicateDecision) -> None:
        for card in self.cards:
            card.set_decision(decision)
        self._decisions_changed()

    def _decisions_changed(self) -> None:
        unresolved = sum(
            candidate.decision == DuplicateDecision.UNRESOLVED
            for candidate in self.candidates
        )
        self.submit_button.setEnabled(unresolved == 0)
        if unresolved:
            self.count_label.setText(
                f"{len(self.candidates)} possible duplicates · {unresolved} unresolved"
            )
        else:
            kept = sum(
                candidate.decision == DuplicateDecision.KEEP
                for candidate in self.candidates
            )
            self.count_label.setText(
                f"{len(self.candidates)} reviewed · {kept} keep · "
                f"{len(self.candidates) - kept} skip"
            )

    def _accept_if_resolved(self) -> None:
        if all(
            candidate.decision != DuplicateDecision.UNRESOLVED
            for candidate in self.candidates
        ):
            self.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().resizeEvent(event)
        narrow = event.size().width() < 820
        for card in self.cards:
            card.set_narrow(narrow)
