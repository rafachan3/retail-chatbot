import sys
import logging
import importlib.util as _ilu
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextBrowser, QGridLayout, QTextEdit, QScrollBar
)
from PyQt6.QtGui import QPixmap, QTextDocument, QFontMetrics, QTextOption, QKeyEvent, QAbstractTextDocumentLayout, QFont
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
            title_label.setStyleSheet("font-weight: bold; color: white;")
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
                "background-color: #1C1C2D; color: white;"
                if is_user
                else "color: white;"
            )
            + " border-radius: 10px; padding: 8px;"
        )

        if is_user:
                bubble.setHtml(f'<div style="text-align: right;">{text}</div>')
        else:
            bubble.setPlainText(text)

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

class ImageRow(QWidget):
    def __init__(self, title: str, image_paths: list[str], parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setSpacing(5)

        # Title Label
        title_label = QLabel(title.lower().capitalize())
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Horizontal layout with arrows + scroll area
        h_layout = QHBoxLayout()
        h_layout.setSpacing(5)

        # Left arrow button
        self.left_btn = QPushButton("◀")
        self.left_btn.setFixedWidth(30)
        self.left_btn.setVisible(False)  # hidden initially
        h_layout.addWidget(self.left_btn)

        # Scroll Area for Images
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedHeight(220)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)  # no border

        # Container for images inside scroll area
        self.image_container = QWidget()
        image_layout = QHBoxLayout()
        image_layout.setSpacing(10)

        for img_path in image_paths:
            pixmap = QPixmap(img_path).scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setFixedSize(150, 200)
            img_label.setScaledContents(True)
            image_layout.addWidget(img_label)

        image_layout.addStretch()
        self.image_container.setLayout(image_layout)
        self.scroll_area.setWidget(self.image_container)

        h_layout.addWidget(self.scroll_area)

        # Right arrow button
        self.right_btn = QPushButton("▶")
        self.right_btn.setFixedWidth(30)
        h_layout.addWidget(self.right_btn)

        layout.addLayout(h_layout)
        self.setLayout(layout)

        # Connect scrolling logic
        self.left_btn.clicked.connect(lambda: self.scroll(-150))
        self.right_btn.clicked.connect(lambda: self.scroll(150))
        bar = self.scroll_area.horizontalScrollBar()
        if bar is not None:
            bar.valueChanged.connect(self.update_arrows)

        self.update_arrows()

    def scroll(self, delta):
        bar = self.scroll_area.horizontalScrollBar()
        if bar is not None:
            bar.setValue(bar.value() + delta)

    def update_arrows(self):
        bar = self.scroll_area.horizontalScrollBar()
        if bar is None:
            return
        self.left_btn.setVisible(bar.value() > 0)
        self.right_btn.setVisible(bar.value() < bar.maximum())

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
                background: #27263C;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #27263C;
                min-height: 30px;
                width: 0px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: #27263C;
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
        if self.input_field is not None:
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
        new_height = (doc_h + 12) if doc_h > 0 else 60  # Add padding or fallback

        if new_height < 60:
            new_height = 60  # minimum height same as button

        if new_height > self.max_input_height:
            new_height = self.max_input_height
            self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.input_field.setFixedHeight(new_height)
    
    def resizeEvent(self, event):
        # Recompute layout when container resizes
        self.on_text_changed()
        super().resizeEvent(event)

    def setup_ui(self):
        # === Main horizontal layout (split screen) ===
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====================
        # === Top Panel (Branding - 12%) ===
        # ====================

        top_panel = QWidget()
        top_panel.setStyleSheet("background-color: #353451;")

        # Create layout for the top panel
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(15, 0, 0, 0)  # Left margin for label spacing
        top_layout.setSpacing(0)

        # Brand label
        brand_label = QLabel("STYLIST")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        font = QFont()
        font.setPointSize(50)
        font.setWeight(QFont.Weight.Black)  # Heavy weight for bold effect
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 10)  # 10px extra space
        brand_label.setFont(font)

        brand_label.setStyleSheet("color: white;")

        # Add label to top panel layout
        top_layout.addWidget(brand_label)

        # ====================
        # === Chat Panel (Chat - 88%) ===
        # ====================

        chat_panel = QVBoxLayout()

        # Chat area
        self.chat_area = QVBoxLayout()
        self.chat_area.setContentsMargins(15, 15, 7, 15)
        self.chat_area.setSpacing(6)

        self.chat_container = QWidget()
        self.chat_container.setLayout(self.chat_area)
        self.chat_container.setStyleSheet("background-color: #27263C;")

        self.chat_area.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.chat_scroll_area = AutoHideScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(self.chat_container)
        self.chat_scroll_area.setStyleSheet("background-color: #27263C; border: none;")

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(15, 0, 15, 15)  # Margins for input area
        input_layout.setSpacing(15)

        input_container = QWidget()
        input_container.setLayout(input_layout)
        input_container.setStyleSheet("""
            background-color: #27263C;
        """)

        self.max_input_height = 100  # Max height for input before scrollbar

        self.input_field = EnterTextEdit()
        self.input_field.setAcceptRichText(False)
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.input_field.setFixedHeight(60)  # Requirement 4
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_field.setPlaceholderText("Type your message...")

        # Apply stylesheet
        self.input_field.setStyleSheet("""
            QTextEdit {
                border: 3px solid #E6E6E6;
                border-radius: 25px;
                padding: 10px;
                font-size: 15px;
                color: white;
                background-color: #353451;
            }
            QTextEdit viewport {
                border-radius: 25px;
                background-color: #353451;
            }
            QScrollBar:vertical {
                background: #353451;
                width: 8px;
                margin: 0;
            }
        """)

        # Ensure vertical alignment (center)
        self.input_field.setViewportMargins(0, 3, 0, 2)

        self.send_btn = QPushButton()
        self.send_btn.setFixedSize(60, 60)  # Circular size
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.hide()  # Initially hidden

        # Style: circle + arrow (using CSS unicode for arrow)
        self.send_btn.setStyleSheet("""
            QPushButton {
                border-radius: 30px;
                background-color: #14577B;
                color: white;
                font-size: 20px;
                font-weight: bold;
                qproperty-icon: none;
            }
            QPushButton:hover {
                background-color: black;
            }
        """)
        self.send_btn.setText("↑")  # Right arrow unicode

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)

        # Connect text change to toggle button visibility
        self.input_field.textChanged.connect(self.on_text_changed)
        self.input_field.enterPressed.connect(self.send_message)
        self.send_btn.clicked.connect(self.send_message)

        # Add to chat panel
        chat_panel.addWidget(self.chat_scroll_area, stretch=1)
        chat_panel.addWidget(input_container)

        # ====================
        # === Add both panels to main layout ===
        # ====================
        main_layout.addWidget(top_panel, stretch=12)
        main_layout.addLayout(chat_panel, stretch=88)

        self.setLayout(main_layout)

    def send_message(self):
        user_text = self.input_field.toPlainText().strip()
        if not user_text:
            return

        # Render user message
        u_msg = ChatBubble(f"{user_text}", is_user=True)
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
        self.input_field.setFixedHeight(60)  # Reset height after sending
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    
    def setup_summary_ui(self, data):

        # 2. Remove original input area
        main_layout = self.layout()
        if not main_layout or main_layout.count() < 2:
            return
        chat_panel_item = main_layout.itemAt(1)
        if chat_panel_item is None:
            return
        chat_panel = chat_panel_item.layout()
        if chat_panel is None:
            return
        input_container_item = chat_panel.itemAt(1) if chat_panel.count() > 1 else None
        if input_container_item is not None:
            input_container_widget = input_container_item.widget()
            if input_container_widget is not None:
                input_container_widget.hide()

        # 3. Create new summary area + recommendations button layout
        new_area = QWidget()
        new_area_layout = QHBoxLayout(new_area)
        new_area_layout.setContentsMargins(0, 0, 0, 0)
        new_area_layout.setSpacing(0)

        # --- Build your detailed summary container here ---
        user_summary = data.get("user_summary", "")

        self.summary_container_widget = QWidget()
        self.summary_container_widget.setStyleSheet("background-color: #27263C;")
        summary_layout = QVBoxLayout(self.summary_container_widget)
        summary_layout.setContentsMargins(15, 15, 15, 15)
        summary_layout.setSpacing(0)

        # Header
        header_label = QLabel("Your selection summary")
        header_label.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: white;
            }
        """)
        header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        summary_layout.addWidget(header_label)

        # User summary text
        if user_summary:
            self.summary_text_widget = QLabel(user_summary)
            self.summary_text_widget.setStyleSheet("""
                QLabel {
                    font-size: 15px;
                    color: white;
                    background-color: #27263C;
                    padding: 10px;
                }
            """)
            self.summary_text_widget.setWordWrap(True)
            self.summary_text_widget.setAlignment(Qt.AlignmentFlag.AlignLeft)
            summary_layout.addWidget(self.summary_text_widget)

        summary_layout.addStretch()


        # Button container for "My recommendations"
        button_container = QWidget()
        button_container.setStyleSheet("background-color: #27263C;")
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 15, 15)
        button_layout.addStretch()

        self.recommendations_btn = QPushButton("My recommendations →")
        self.recommendations_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recommendations_btn.setStyleSheet("""
            QPushButton {
                background-color: #27263C;
                color: white;
                border-radius: 12px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: black;
            }
        """)

        button_layout.addWidget(self.recommendations_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        items = data.get("outfit_items", [])
        if not items:
            items.append(data.get("single_item_type", ""))

        self.recommendations_btn.clicked.connect(lambda: self.recommendation_setup(items))

        new_area_layout.addWidget(self.summary_container_widget)
        new_area_layout.addWidget(button_container)

        # Insert the new area widget into the chat panel layout at position 1
        if hasattr(chat_panel, 'insertWidget'):
            chat_panel.insertWidget(1, new_area)  # type: ignore[attr-defined]

        # Log recommendations (no UI modification)
        try:
            logging.info("Summary UI displayed; generating recommendations...")
            rec_path = Path(__file__).parent / "recommendation" / "backend_recs.py"
            spec = _ilu.spec_from_file_location("recommendation_backend", str(rec_path))
            if spec and spec.loader:
                mod = _ilu.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                # Embedding-only flow (no TF-IDF fallback)
                rec_dir = Path(__file__).parent / 'recommendation'
                mode = data.get('mode')
                get_embed = getattr(mod, 'get_embedding_recommender', None)
                if not get_embed:
                    logging.error("Embedding recommender unavailable (get_embedding_recommender missing).")
                else:
                    try:
                        emb_rec = get_embed(rec_dir)
                        if mode == 'outfit':
                            out_struct = emb_rec.recommend_outfit_from_preferences(data, top_k=3)
                            logging.info("[embed] Outfit recommendations: %s", out_struct)
                        else:
                            single = emb_rec.recommend_from_preferences(data, top_k=3)
                            logging.info("[embed] Single-item recommendations: %s", single)
                    except Exception as e_embed:
                        logging.error("Embedding recommendation failed: %s", e_embed)
        except Exception as e:
            logging.warning("Recommendation logging failed: %s", e)

    def recommendation_setup(self, items):
        parent_widget = self
        old_layout = parent_widget.layout()

        # --- Save existing widgets before removing layout ---
        chat_area = self.chat_scroll_area
        summary_container = getattr(self, "summary_container_widget", None)

        # Reparent to avoid deletion
        chat_area.setParent(None)
        if summary_container:
            summary_container.setParent(None)

        # Remove old layout
        QWidget().setLayout(old_layout)

        # --- New horizontal layout ---
        main_layout = QHBoxLayout()
        parent_widget.setLayout(main_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left panel (20%) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Make chat area not take all space
        chat_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(chat_area, stretch=3)  # 3 parts of vertical space

        if summary_container:
            summary_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            left_layout.addWidget(summary_container, stretch=1)  # 1 part of vertical space

        # --- Middle panel (60%) ---
        middle_panel = QWidget()
        middle_panel.setStyleSheet("background-color: white;")
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel("My recommendations")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #2A2A3D;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        middle_layout.addWidget(title_label)

        for item in items:
            image_path = ['/Users/hugoguideau/retail-chatbot/0005720_coming-soon-page_550.jpeg']*10
            item_row = ImageRow(item, image_path)
            middle_layout.addWidget(item_row)

        middle_layout.addStretch(1)

        # --- Wrap the middle panel in a scroll area ---
        middle_scroll_area = QScrollArea()
        middle_scroll_area.setWidgetResizable(True)
        middle_scroll_area.setWidget(middle_panel)

        # --- Right panel (20%) ---
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #2A2A3D;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)

        bucket_label = QLabel("Bucket zone")
        bucket_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        right_layout.addWidget(bucket_label)
        right_layout.addStretch()

        # --- Add to horizontal layout ---
        main_layout.addWidget(left_panel, 2)   # 20%
        main_layout.addWidget(middle_scroll_area, 6) # 60%
        main_layout.addWidget(right_panel, 2)  # 20%

    def handle_payload(self, payload: dict):
        # Render backend messages
        for i, msg in enumerate(payload.get("messages", [])):
            if i == 0:
                b_msg = ChatBubble(f"{msg}", is_user=False, title="Bot")
            else:
                b_msg = ChatBubble(f"{msg}", is_user=False)
            self.chat_area.insertWidget(self.chat_area.count(), b_msg, alignment=Qt.AlignmentFlag.AlignBottom)
        # Simple presentation of choices (if any)
        if payload.get("expect") == "choice" and payload.get("choices"):
            hint = " / ".join(payload["choices"])  # simple inline hint
            hint_msg = ChatBubble(f"Options: {hint}", is_user=False, title="Bot")
            self.chat_area.insertWidget(self.chat_area.count(), hint_msg, alignment=Qt.AlignmentFlag.AlignBottom)
        
        # Show summary in bucket when requested
        if payload.get("show_summary"):
            self.setup_summary_ui(payload.get("data", {}))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", force=True)
    app = QApplication(sys.argv)
    chatbot = ChatBotUI()
    chatbot.showMaximized()
    sys.exit(app.exec())