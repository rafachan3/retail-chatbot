import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class ChatBotUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stylist ChatBot")
        self.setup_ui()

    def setup_ui(self):
        # === Main vertical layout ===
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # === Brand name ===
        brand_label = QLabel("STYLIST")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")

        # === Image / Logo ===
        image_label = QLabel()
        pixmap = QPixmap("chatbot_logo.png")  # Replace with your image
        pixmap = pixmap.scaledToWidth(80, Qt.TransformationMode.SmoothTransformation)
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # === Scrollable chat area ===
        self.chat_area = QVBoxLayout()
        self.chat_area.setAlignment(Qt.AlignmentFlag.AlignTop)

        chat_container = QWidget()
        chat_container.setLayout(self.chat_area)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(chat_container)
        scroll_area.setStyleSheet("background-color: #f5f5f5; border: none;")

        # === Input area ===
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.returnPressed.connect(self.send_message)
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(send_button)

        # === Add to main layout ===
        main_layout.addWidget(brand_label)
        main_layout.addWidget(image_label)
        main_layout.addWidget(scroll_area, stretch=1)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

    def add_message(self, text, is_user=True):
        # === Message bubble layout ===
        bubble_layout = QHBoxLayout()
        bubble_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
        )

        # === Bubble container ===
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        bubble.setStyleSheet(
            f"""
            background-color: {'#e0e0e0' if is_user else '#ffffff'};
            border-radius: 10px;
            padding: 10px;
            max-width: 60%;
            font-size: 14px;
            """
        )

        bubble_layout.addWidget(bubble)
        self.chat_area.addLayout(bubble_layout)

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