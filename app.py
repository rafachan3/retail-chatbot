import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextBrowser, QGridLayout, QTextEdit
)
from PyQt6.QtGui import QPixmap, QTextDocument, QFontMetrics, QTextOption, QKeyEvent
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal

class ChatBubble(QWidget):
    def __init__(self, text, is_user, title):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        title_label.setObjectName("title")
        title_label.setStyleSheet(f"""
            QLabel#title {{
                font-weight: bold;
                color: #666666;
                font-size: 12px;
            }}
        """)

        bubble_layout = QHBoxLayout()
        bubble_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel()
        label.setText(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        label.setTextFormat(Qt.TextFormat.RichText)

        if is_user:
            label.setObjectName('user-bubble')
            label.setStyleSheet(f"""
                QLabel#user-bubble {{
                    background-color: #0A84FF;  /* bleu iMessage */
                    color: white;
                    border-radius: 17px;
                    padding: 10px 15px;
                    border: none;
                }}
            """)
        else:
            label.setObjectName('bot-bubble')
            label.setStyleSheet(f"""
                QLabel#bot-bubble {{
                    background-color: #E5E5EA;  /* gris très clair */
                    color: #1C1C1E;             /* texte presque noir */
                    border-radius: 17px;
                    padding: 10px 15px;
                    border: none;
                }}
            """)

        if is_user:
            title_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            outer_layout.addWidget(title_label)
            bubble_layout.addStretch()
            bubble_layout.addWidget(label)
        else:
            outer_layout.addWidget(title_label)
            bubble_layout.addWidget(label)
            bubble_layout.addStretch()
        
        outer_layout.addLayout(bubble_layout)
        self.setLayout(outer_layout)

class AutoHideScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.scrollbar = self.verticalScrollBar()
        self._timer = QTimer()
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
                self._timer.stop()  # Don't hide while pressed
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._scrollbar_pressed = False
                if not self._mouse_inside:
                    self._timer.start()  # Start hide timer if mouse not inside
            elif event.type() == QEvent.Type.Leave:
                # If scrollbar loses mouse focus and not pressed, start timer
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

    def show_scrollbar_handle(self):
        self.scrollbar.setStyleSheet("""
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
        """)

    def hide_scrollbar_handle(self):
        self.scrollbar.setStyleSheet("""
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
        """)

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
        self.setup_ui()

    def on_text_changed(self):
        text = self.input_field.toPlainText().strip()

        # Show or hide send button
        if text:
            self.send_btn.show()
        else:
            self.send_btn.hide()

        # Get document size (more accurate)
        doc_size = self.input_field.document().documentLayout().documentSize()
        new_height = int(doc_size.height()) + 12  # Add some padding

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

        if user_text:
            u_msg = ChatBubble(f"{user_text}", is_user=True, title="You")
            self.chat_area.insertWidget(self.chat_area.count(), u_msg, alignment=Qt.AlignmentFlag.AlignBottom)

            bot_response = self.get_bot_response(user_text)
            b_msg = ChatBubble(f"{bot_response}", is_user=False, title="Bot")
            self.chat_area.insertWidget(self.chat_area.count(), b_msg, alignment=Qt.AlignmentFlag.AlignBottom)

            # Scroll to the bottom of the chat area
            v_scrollbar = self.chat_scroll_area.verticalScrollBar()
            QTimer.singleShot(100, lambda: v_scrollbar.setValue(v_scrollbar.maximum()))

            self.input_field.clear()
            self.send_btn.hide()

            self.input_field.setFixedHeight(40)  # Reset height after sending
            self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)



    def get_bot_response(self, message):
        return f"Echo: {message}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    chatbot = ChatBotUI()
    chatbot.showMaximized()
    sys.exit(app.exec())