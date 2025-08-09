import sys
import importlib.util as _ilu
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextBrowser, QGridLayout, QTextEdit, QScrollBar
)
from PyQt6.QtGui import QPixmap, QTextDocument, QFontMetrics, QTextOption, QKeyEvent, QAbstractTextDocumentLayout
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from typing import cast, Optional

class ChatBubble(QWidget):
    """A chat bubble that expands vertically to fit multi-line text.

    Uses QTextBrowser to reliably compute document height for the given width,
    avoiding QLabel's occasional one-line height calculation on macOS.
    """

    def __init__(self, text: str, is_user: bool = False, title: Optional[str] = None):
        super().__init__()
        self._hpad = 16  # total horizontal padding (8px left + 8px right)
        self._vpad = 16  # total vertical padding (8px top + 8px bottom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: bold; color: #555; margin: 0 6px;")
            layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        # Use QTextBrowser so we can control wrapping width and compute height
        bubble = QTextBrowser()
        bubble.setPlainText(text)
        bubble.setReadOnly(True)
        bubble.setFrameStyle(QFrame.Shape.NoFrame)
        bubble.setOpenExternalLinks(False)
        bubble.setOpenLinks(False)
        bubble.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        bubble.setStyleSheet(
            (
                "background-color: #e0f7ff; color: #003b57; border: 1px solid #b3e5ff;"
                if is_user
                else "background-color: #ffffff; color: #333; border: 1px solid #e0e0e0;"
            )
            + " border-radius: 10px; padding: 8px;"
        )

        self.bubble = bubble
        layout.addWidget(self.bubble, 0, Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        # Initial sizing
        self._update_size()

    def _update_size(self) -> None:
        try:
            avail = max(220, min(self.width() - 40, 640))
            if avail < 100:
                avail = 220
            # Set the text width for proper wrapping, accounting for padding
            doc = self.bubble.document()
            if doc is None:
                return
            doc.setTextWidth(max(10.0, float(avail - self._hpad)))
            # Apply width and compute height from the document
            self.bubble.setFixedWidth(avail)
            # Prefer layout's documentSize when available
            layout = doc.documentLayout()
            if layout is not None:
                sizef = layout.documentSize()
                doc_h = int(sizef.height())
            else:
                doc_h = int(doc.size().height())
            self.bubble.setFixedHeight(doc_h + self._vpad)
        except Exception:
            pass

    def resizeEvent(self, event):
        # Recompute layout when container resizes
        self._update_size()
        super().resizeEvent(event)


class AutoHideScrollArea(QScrollArea):
    # Help type checkers understand instance attribute types
    scrollbar: QScrollBar

    def __init__(self) -> None:
        super().__init__()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.scrollbar = cast(QScrollBar, self.verticalScrollBar())
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.hide_scrollbar_handle)

        self._mouse_inside = False
        self._scrollbar_pressed = False

        # Initially hide scrollbar handle
        self.hide_scrollbar_handle()

        self.setMouseTracking(True)
        # Listen to scrollbar events to track pressing
        self.scrollbar.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.scrollbar:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._scrollbar_pressed = True
                self.show_scrollbar_handle()
                self._timer.stop()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._scrollbar_pressed = False
                if not self._mouse_inside:
                    self._timer.start()
            elif event.type() == QEvent.Type.Leave:
                if not self._scrollbar_pressed and not self._mouse_inside:
                    self._timer.start()
            elif event.type() == QEvent.Type.Enter:
                self._mouse_inside = True
                self.show_scrollbar_handle()
                self._timer.stop()
            elif event.type() == QEvent.Type.MouseMove:
                self._mouse_inside = True
                self.show_scrollbar_handle()
                self._timer.stop()
        return super().eventFilter(obj, event)

    def enterEvent(self, event):
        self._mouse_inside = True
        self.show_scrollbar_handle()
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._mouse_inside = False
        if not self._scrollbar_pressed:
            self._timer.start()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        self.show_scrollbar_handle()
        self._timer.start()
        super().wheelEvent(event)

    def show_scrollbar_handle(self) -> None:
        self.scrollbar.setStyleSheet(
            """
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 100, 100, 0.6);
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(100, 100, 100, 1);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0;
                border: none;
            }
            """
        )

    def hide_scrollbar_handle(self) -> None:
        self.scrollbar.setStyleSheet(
            """
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: transparent;
                min-height: 30px;
                width: 0px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0;
                border: none;
            }
            """
        )

class EnterTextEdit(QTextEdit):
    enterPressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.enterPressed.emit()
        else:
            super().keyPressEvent(event)

class ChatBotUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stylist ChatBot")
        # Load backend session from user-preferences/backend-user-preferences.py
        backend_path = Path(__file__).parent / "user-preferences" / "backend-user-preferences.py"
        spec = _ilu.spec_from_file_location("preferences_backend", str(backend_path))
        if not spec or not spec.loader:
            raise RuntimeError("Failed to load backend-user-preferences.py")
        module = _ilu.module_from_spec(spec)
        import sys as _sys
        _sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        Session = getattr(module, "Session")
        self.session = Session()

        self.setup_ui()
        # Bootstrap conversation
        payload = self.session.process(None)
        self.handle_payload(payload)

    def on_text_changed(self):
        text = self.input_field.toPlainText().strip()

        # Show or hide send button
        if text:
            self.send_btn.show()
        else:
            self.send_btn.hide()

        # Get document size (with guards for type checkers)
        doc: Optional[QTextDocument] = self.input_field.document()
        doc_h = 0
        if doc is not None:
            layout: Optional[QAbstractTextDocumentLayout] = doc.documentLayout()
            if layout is not None:
                sizef = layout.documentSize()
                try:
                    doc_h = int(sizef.height())
                except Exception:
                    doc_h = 0
        new_height = (doc_h + 12) if doc_h > 0 else 40  # Add padding or fallback

        if new_height < 40:
            new_height = 40  # minimum height same as button

        if new_height > self.max_input_height:
            new_height = self.max_input_height
            self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.input_field.setFixedHeight(new_height)

    def setup_ui(self):
        # === Main horizontal layout (split screen) ===
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ====================
        # === Left Panel (Articles Bucket - 70%) ===
        # ====================
        left_panel = QVBoxLayout()

        # Title
        bucket_title = QLabel("Your Bucket")
        bucket_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        bucket_title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Articles zone
        self.articles_layout = QGridLayout()  # Can be used to display articles in a grid bucket format

        articles_widget = QWidget()
        articles_widget.setLayout(self.articles_layout)

        articles_scroll = QScrollArea()
        articles_scroll.setWidgetResizable(True)
        articles_scroll.setWidget(articles_widget)
        articles_scroll.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc;")

        # Confirm button
        confirm_button = QPushButton("Confirm Bucket")
        confirm_button.setStyleSheet("padding: 10px; font-weight: bold; background-color: #4CAF50; color: white;")

        # Add to left panel
        left_panel.addWidget(bucket_title)
        left_panel.addWidget(articles_scroll, stretch=1)
        left_panel.addWidget(confirm_button)

        # ====================
        # === Right Panel (Chat - 30%) ===
        # ====================
        right_panel = QVBoxLayout()

        # Brand label
        brand_label = QLabel("STYLIST")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")

        # Logo image
        image_label = QLabel()
        pixmap = QPixmap("chatbot_logo.png")
        pixmap = pixmap.scaledToWidth(80, Qt.TransformationMode.SmoothTransformation)
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Chat area
        self.chat_area = QVBoxLayout()
        self.chat_area.insertStretch(0, 1)

        chat_container = QWidget()
        chat_container.setLayout(self.chat_area)

        self.chat_scroll_area = AutoHideScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(chat_container)
        self.chat_scroll_area.setStyleSheet("background-color: #f5f5f5; border: none;")

        # Input area
        input_layout = QHBoxLayout()
        self.max_input_height = 100  # Max height for input before scrollbar

        self.input_field = EnterTextEdit()
        self.input_field.setAcceptRichText(False)
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.input_field.setFixedHeight(40)  # Start height same as button
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 6px;
                font-size: 14px;
            }
        """)

        self.send_btn = QPushButton()
        self.send_btn.setFixedSize(40, 40)  # Circular size
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.hide()  # Initially hidden

        # Style: circle + arrow (using CSS unicode for arrow)
        self.send_btn.setStyleSheet("""
            QPushButton {
                border-radius: 20px;
                background-color: #0078d7;
                color: white;
                font-size: 20px;
                font-weight: bold;
                qproperty-icon: none;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        self.send_btn.setText("→")  # Right arrow unicode

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)

        # Connect text change to toggle button visibility
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.enterPressed.connect(self.send_message)
        self.send_btn.clicked.connect(self.send_message)

        # Add to right panel
        right_panel.addWidget(brand_label)
        right_panel.addWidget(image_label)
        right_panel.addWidget(self.chat_scroll_area, stretch=1)
        right_panel.addLayout(input_layout)

        # ====================
        # === Add both panels to main layout ===
        # ====================
        main_layout.addLayout(left_panel, stretch=7)
        main_layout.addLayout(right_panel, stretch=3)

        self.setLayout(main_layout)

    def send_message(self):
        user_text = self.input_field.toPlainText().strip()
        if not user_text:
            return

        # Render user message
        u_msg = ChatBubble(f"{user_text}", is_user=True, title="You")
        self.chat_area.insertWidget(self.chat_area.count(), u_msg, alignment=Qt.AlignmentFlag.AlignBottom)

        # Route to backend
        payload = self.session.process(user_text)
        self.handle_payload(payload)

        # Scroll to the bottom of the chat area (guard for type checkers)
        v_scrollbar = self.chat_scroll_area.verticalScrollBar()
        if v_scrollbar is not None:
            QTimer.singleShot(100, lambda: v_scrollbar.setValue(v_scrollbar.maximum()))

        # Reset input
        self.input_field.clear()
        self.send_btn.hide()
        self.input_field.setFixedHeight(40)  # Reset height after sending
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def display_user_summary_in_bucket(self, data: dict):
        """Display user's preferences summary and recommendations placeholder in the bucket section."""
        # Clear any existing content in the articles layout
        for i in reversed(range(self.articles_layout.count())):
            child = self.articles_layout.itemAt(i)
            if child and child.widget():
                widget = child.widget()
                if widget:
                    widget.deleteLater()
        
        # Get the user summary from data
        user_summary = data.get("user_summary", "")
        
        # Create a container widget for the summary
        summary_container = QWidget()
        summary_layout = QVBoxLayout(summary_container)
        summary_layout.setContentsMargins(15, 15, 15, 15)
        summary_layout.setSpacing(15)
        
        # Header
        header_label = QLabel("Your Selection Summary")
        header_label.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
            }
        """)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(header_label)
        
        # User summary
        if user_summary:
            summary_text = QLabel(user_summary)
            summary_text.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #34495e;
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid #e9ecef;
                    line-height: 1.6;
                }
            """)
            summary_text.setWordWrap(True)
            summary_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
            summary_layout.addWidget(summary_text)
        
        # Recommendations placeholder
        recommendations_header = QLabel("🎯 Personalized Recommendations")
        recommendations_header.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #27ae60;
                margin-top: 10px;
                margin-bottom: 5px;
            }
        """)
        recommendations_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(recommendations_header)
        
        recommendations_placeholder = QLabel(
            "🔄 Our AI stylist is analyzing your preferences...\n\n"
            "Your curated recommendations will appear here shortly!\n\n"
            "This will include:\n"
            "• Perfectly matched items based on your style\n"
            "• Size and fit recommendations\n"
            "• Price comparisons from top retailers"
        )
        recommendations_placeholder.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #7f8c8d;
                background-color: #ffffff;
                padding: 20px;
                border: 2px dashed #3498db;
                border-radius: 10px;
                text-align: center;
                line-height: 1.8;
            }
        """)
        recommendations_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recommendations_placeholder.setWordWrap(True)
        summary_layout.addWidget(recommendations_placeholder)
        
        # Add stretch to push content to top
        summary_layout.addStretch()
        
        # Add the summary container to the articles layout
        self.articles_layout.addWidget(summary_container, 0, 0)

    def handle_payload(self, payload: dict):
        # Render backend messages
        for msg in payload.get("messages", []):
            b_msg = ChatBubble(f"{msg}", is_user=False, title="Bot")
            self.chat_area.insertWidget(self.chat_area.count(), b_msg, alignment=Qt.AlignmentFlag.AlignBottom)
        # Simple presentation of choices (if any)
        if payload.get("expect") == "choice" and payload.get("choices"):
            hint = " / ".join(payload["choices"])  # simple inline hint
            hint_msg = ChatBubble(f"Options: {hint}", is_user=False, title="Bot")
            self.chat_area.insertWidget(self.chat_area.count(), hint_msg, alignment=Qt.AlignmentFlag.AlignBottom)
        
        # Show summary in bucket when requested
        if payload.get("show_summary"):
            self.display_user_summary_in_bucket(payload.get("data", {}))
            
        # Disable input when done
        if payload.get("done"):
            self.input_field.setDisabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    chatbot = ChatBotUI()
    chatbot.showMaximized()
    sys.exit(app.exec())