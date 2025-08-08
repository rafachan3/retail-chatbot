import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextBrowser, QGridLayout
)
from PyQt6.QtGui import QPixmap, QTextDocument, QFontMetrics
from PyQt6.QtCore import Qt, QTimer


class ChatBotUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stylist ChatBot")
        self.setup_ui()

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
        self.chat_area.setAlignment(Qt.AlignmentFlag.AlignTop)

        chat_container = QWidget()
        chat_container.setLayout(self.chat_area)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(chat_container)
        scroll_area.setStyleSheet("background-color: #f5f5f5; border: none;")

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.returnPressed.connect(self.send_message)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(send_button)

        # Add to right panel
        right_panel.addWidget(brand_label)
        right_panel.addWidget(image_label)
        right_panel.addWidget(scroll_area, stretch=1)
        right_panel.addLayout(input_layout)

        # ====================
        # === Add both panels to main layout ===
        # ====================
        main_layout.addLayout(left_panel, stretch=7)
        main_layout.addLayout(right_panel, stretch=3)

        self.setLayout(main_layout)


    def add_message(self, text, is_user=True):
        # Layout wrapper
        message_layout = QHBoxLayout()
        message_layout.setContentsMargins(5, 5, 5, 5)

        # Bubble widget
        bubble = QTextBrowser()
        bubble.setText(text)
        bubble.setReadOnly(True)
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bubble.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setOpenExternalLinks(True)

        # Style
        bubble.setStyleSheet(
            f"""
            QTextBrowser {{
                background-color: {'#e0e0e0' if is_user else '#f5f5f5'};
                border-radius: 10px;
                padding: 10px;
                font-size: 14px;
            }}
            """
        )

        # Measurements
        # Get max width from scroll area viewport
        max_bubble_width = int(self.width() * 0.6 * 0.3)
        
        bubble.setMaximumWidth(max_bubble_width)
        doc = QTextDocument()
        doc.setDefaultFont(bubble.font())
        doc.setTextWidth(max_bubble_width)
        doc.setHtml(bubble.toHtml())
        height = int(doc.size().height()) + 20
        bubble.setFixedHeight(height)

        # Alignment
        message_layout.setAlignment(Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)
        message_layout.addWidget(bubble)
        self.chat_area.addLayout(message_layout)

        # Scroll to bottom
        QApplication.processEvents()
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            QTimer.singleShot(0, lambda: scroll_area.verticalScrollBar().setValue(scroll_area.verticalScrollBar().maximum()))


    def send_message(self):
        user_text = self.input_field.text().strip()
        if not user_text:
            return

        self.add_message(user_text, is_user=True)
        self.input_field.clear()

        bot_response = self.get_bot_response(user_text)
        self.add_message(bot_response, is_user=False)

    def get_bot_response(self, message):
        return f"Echo: {message}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    chatbot = ChatBotUI()
    chatbot.showMaximized()
    sys.exit(app.exec())