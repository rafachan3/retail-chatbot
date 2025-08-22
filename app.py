import sys
import logging
import importlib.util as _ilu
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextBrowser, QGridLayout, QTextEdit, QScrollBar
)
from PyQt6.QtGui import QPixmap, QTextDocument, QFontMetrics, QTextOption, QAbstractTextDocumentLayout, QFont
from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from typing import cast, Optional

class ChatBubble(QWidget):
    """A custom widget for displaying chat messages in bubble format.
    
    Creates a styled chat bubble with appropriate alignment and colors
    for either user or bot messages.
    """
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
    """A widget for displaying a horizontal row of product images with titles.
    
    Shows product recommendations in a scrollable horizontal layout with
    product images, names, and details.
    """
    def __init__(self, title: str, image_data: list[dict], parent=None):
        """
        Args:
            title: The title for the row
            image_data: List of dicts with 'image_path' and 'prod_name' keys
        """
        super().__init__(parent)
        
        # Debug logging
        logging.info(f"ImageRow created with title: '{title}' and {len(image_data)} items")

        layout = QVBoxLayout()
        layout.setSpacing(5)

        # Title Label
        display_title = title.lower().capitalize() if title else "Items"
        title_label = QLabel(display_title)
        title_label.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: #2A2A3D; 
            padding: 10px 0px 5px 0px;
            margin-bottom: 5px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
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
        self.scroll_area.setFixedHeight(295)  # Increased to accommodate product names and style
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)  # no border

        # Container for images inside scroll area
        self.image_container = QWidget()
        image_layout = QHBoxLayout()
        image_layout.setSpacing(10)

        for item in image_data:
            # Handle both old format (strings) and new format (dicts)
            if isinstance(item, str):
                img_path = item
                prod_name = "Product"  # Default name for backward compatibility
                style = ""  # Default empty style
            else:
                img_path = item.get('image_path', '')
                prod_name = item.get('prod_name', 'Unknown Product')
                style = item.get('style', '')
            
            # Create container for image + text
            item_container = QWidget()
            item_layout = QVBoxLayout(item_container)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)
            
            # Image
            pixmap = QPixmap(img_path).scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setFixedSize(150, 200)
            img_label.setScaledContents(True)
            item_layout.addWidget(img_label)
            
            # Product name label
            name_label = QLabel(prod_name)
            name_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                color: #2A2A3D;
                background-color: white;
                padding: 2px;
            """)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFixedWidth(150)
            name_label.setMaximumHeight(25)
            item_layout.addWidget(name_label)
            
            # Style label (if style information is available)
            if style:
                style_label = QLabel(f"Style: {style}")
                style_label.setStyleSheet("""
                    font-size: 10px;
                    color: #666666;
                    background-color: #f0f0f0;
                    padding: 2px;
                    border-radius: 3px;
                """)
                style_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                style_label.setWordWrap(True)
                style_label.setFixedWidth(150)
                style_label.setMaximumHeight(20)
                item_layout.addWidget(style_label)
            
            image_layout.addWidget(item_container)

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
    """A scroll area that automatically hides its scrollbars when not needed.
    
    Provides a cleaner interface by only showing scrollbars when content
    exceeds the visible area.
    """
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
    """A custom text edit widget that emits a signal when Enter is pressed.
    
    Allows for easy handling of Enter key presses to send messages,
    while supporting Shift+Enter for new lines.
    """
    enterPressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.enterPressed.emit()
        else:
            super().keyPressEvent(event)


class ChatBotUI(QWidget):
    """Main application window for the retail chatbot.
    
    Provides a conversational interface for users to specify their clothing
    preferences and receive personalized recommendations. Features include:
    - Interactive conversation flow for collecting preferences
    - Size recommendations based on body measurements
    - Product recommendations with images organized by category
    - Responsive UI that adapts to different conversation stages
    """
    def __init__(self):
        """Initialize the chatbot UI and load the conversation backend."""
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
        """Setup the main user interface layout and components."""
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
    
    def group_by_requested_items(self, user_requested_items, recommendations):
        """Group recommendations by their requested item type field.
        
        This is a simple and reliable approach that uses the requested_item_type
        field that was added to each recommendation during generation.
        
        Args:
            user_requested_items: List of item types the user requested
            recommendations: List of recommendation objects with requested_item_type field
            
        Returns:
            Dictionary mapping user requested items to their recommendations
        """
        from collections import defaultdict
        
        user_item_groups = defaultdict(list)
        
        # First, group recommendations by their requested_item_type field
        for rec in recommendations:
            requested_item = rec.get("requested_item_type", "")
            if requested_item:
                user_item_groups[requested_item].append(rec)
        
        # Convert to regular dict and ensure all user requested items have entries
        result = {}
        for user_item in user_requested_items:
            result[user_item] = user_item_groups.get(user_item, [])
        
        # Add any items that weren't in user_requested_items but have recommendations
        for requested_item, recs in user_item_groups.items():
            if requested_item not in result:
                result[requested_item] = recs
        
        logging.info(f"Grouped recommendations: {[(k, len(v)) for k, v in result.items()]}")
        return result
    
    def convert_recommendations_to_image_data(self, recommendations, rec_dir):
        """Convert recommendation objects to image data format for UI display.
        
        Args:
            recommendations: List of recommendation objects from the backend
            rec_dir: Directory containing the recommendation images
            
        Returns:
            List of image data dictionaries with paths and product info
        """
        from pathlib import Path
        
        image_data = []
        images_dir = rec_dir / "images"
        placeholder_path = rec_dir.parent / "0005720_coming-soon-page_550.jpeg"
        
        for rec in recommendations:
            article_id_raw = rec.get("article_id", "")
            if not article_id_raw:
                continue
            
            # Convert to string and handle zero-padding for 10-digit article IDs
            article_id_str = str(article_id_raw)
            if len(article_id_str) == 9:  # Missing leading zero
                article_id_str = "0" + article_id_str
                
            # Look for image file with article_id name (try different extensions)
            image_path = None
            for ext in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
                potential_path = images_dir / f"{article_id_str}{ext}"
                if potential_path.exists():
                    image_path = str(potential_path)
                    break
            
            # Use placeholder if no image found
            if not image_path and placeholder_path.exists():
                image_path = str(placeholder_path)
            
            if image_path:
                image_data.append({
                    "image_path": image_path,
                    "product_type_name": rec.get("product_type_name", "Unknown"),
                    "style": rec.get("style", "Unknown"),
                    "article_id": article_id_str,
                    "prod_name": rec.get("prod_name", "Unknown Product")
                })
        
        return image_data
    
    def setup_summary_ui(self, data):
        """Setup the summary UI showing user preferences and size recommendations."""
        
        # Store user data for later use
        self.current_user_data = data

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

        # Size recommendation
        try:
            # Import the size recommendation function
            rec_path = Path(__file__).parent / "recommendation" / "backend_recs.py"
            spec = _ilu.spec_from_file_location("recommendation_backend", str(rec_path))
            if spec and spec.loader:
                mod = _ilu.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                
                get_size = getattr(mod, 'get_recommended_size', None)
                if get_size:
                    rec_dir = Path(__file__).parent / 'recommendation'
                    recommended_size = get_size(data, rec_dir)
                    
                    if recommended_size:
                        size_text = f"📏 The recommended size for your clothing pieces is: {recommended_size}"
                        self.size_widget = QLabel(size_text)
                        self.size_widget.setStyleSheet("""
                            QLabel {
                                font-size: 16px;
                                font-weight: bold;
                                color: #4CAF50;
                                background-color: #1a1a2e;
                                padding: 12px;
                                border-radius: 8px;
                                border: 2px solid #4CAF50;
                            }
                        """)
                        self.size_widget.setWordWrap(True)
                        self.size_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        summary_layout.addWidget(self.size_widget)
        except Exception as e:
            logging.warning(f"Failed to get size recommendation: {e}")

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

        self.recommendations_btn.clicked.connect(lambda: self.recommendation_setup(data))

        new_area_layout.addWidget(self.summary_container_widget)
        new_area_layout.addWidget(button_container)

        # Insert the new area widget into the chat panel layout at position 1
        if hasattr(chat_panel, 'insertWidget'):
            chat_panel.insertWidget(1, new_area)  # type: ignore[attr-defined]

        # Log recommendations and store them for UI use
        self.current_recommendations = []
        try:
            logging.info("Summary UI displayed; generating recommendations...")
            rec_path = Path(__file__).parent / "recommendation" / "backend_recs.py"
            spec = _ilu.spec_from_file_location("recommendation_backend", str(rec_path))
            if spec and spec.loader:
                mod = _ilu.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                # Embedding-only flow
                rec_dir = Path(__file__).parent / 'recommendation'
                mode = data.get('mode')
                get_embed = getattr(mod, 'get_embedding_recommender', None)
                if not get_embed:
                    logging.error("Embedding recommender unavailable (get_embedding_recommender missing).")
                else:
                    try:
                        emb_rec = get_embed(rec_dir)
                        if mode == 'outfit':
                            recommendations = emb_rec.recommend_outfit_from_preferences(data, top_k=3)
                            logging.info("[embed] Outfit recommendations: %s", recommendations)
                        else:
                            recommendations = emb_rec.recommend_from_preferences(data, top_k=3)
                            logging.info("[embed] Single-item recommendations: %s", recommendations)
                        
                        # Store recommendations for use in recommendation_setup
                        self.current_recommendations = recommendations
                    except Exception as e_embed:
                        logging.error("Embedding recommendation failed: %s", e_embed)
        except Exception as e:
            logging.warning("Recommendation logging failed: %s", e)

    def recommendation_setup(self, data=None):
        """Setup the recommendation display UI showing categorized product images.
        
        Transitions from the conversation interface to the recommendation interface,
        showing products grouped by the user's requested item types.
        
        Args:
            data: User preference data collected during conversation
        """
        if data is None:
            # Fallback to stored data if available
            data = getattr(self, 'current_user_data', {})
        
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

        # Get real recommendation images
        try:
            # Import the extract function
            rec_path = Path(__file__).parent / "recommendation" / "backend_recs.py"
            spec = _ilu.spec_from_file_location("recommendation_backend", str(rec_path))
            if spec and spec.loader:
                mod = _ilu.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                
                extract_images = getattr(mod, 'extract_recommendation_images', None)
                if extract_images and hasattr(self, 'current_recommendations'):
                    rec_dir = Path(__file__).parent / 'recommendation'
                    image_data = extract_images(self.current_recommendations, rec_dir)
                    
                    # Get user's requested items to use as category titles
                    user_requested_items = []
                    if data.get("mode") == "outfit":
                        user_requested_items = data.get("outfit_items", [])
                    else:
                        single_item = data.get("single_item_type", "")
                        if single_item:
                            user_requested_items = [single_item]
                    
                    # Group recommendations by user's requested item types - SIMPLIFIED
                    user_item_groups = self.group_by_requested_items(user_requested_items, self.current_recommendations)
                    
                    # Debug logging
                    logging.info(f"User requested items: {user_requested_items}")
                    for user_item, items in user_item_groups.items():
                        logging.info(f"Group '{user_item}': {len(items)} items")
                        for item in items[:3]:  # Log first 3 items
                            logging.info(f"  - {item.get('prod_name', 'Unknown')} ({item.get('product_type_name', 'Unknown type')})")
                    
                    # Create image rows for each user-requested item category
                    for user_item, items in user_item_groups.items():
                        if items:  # Only create row if there are items
                            logging.info(f"Creating ImageRow for '{user_item}' with {len(items)} items")
                            # Ensure title is properly formatted
                            display_title = str(user_item).strip()
                            if not display_title:
                                display_title = "Items"
                            
                            # Convert recommendation objects to image data format
                            image_data_for_row = self.convert_recommendations_to_image_data(items, rec_dir)
                            item_row = ImageRow(display_title, image_data_for_row)
                            middle_layout.addWidget(item_row)
            else:
                # Fallback to placeholder image if extraction fails
                placeholder_path = str(Path(__file__).parent / '0005720_coming-soon-page_550.jpeg')
                placeholder_data = [{'image_path': placeholder_path, 'prod_name': 'Coming Soon'}] * 5
                item_row = ImageRow("Recommendations", placeholder_data)
                middle_layout.addWidget(item_row)
        except Exception as e:
            logging.warning(f"Failed to load recommendation images: {e}")
            # Fallback to placeholder image
            placeholder_path = str(Path(__file__).parent / '0005720_coming-soon-page_550.jpeg')
            placeholder_data = [{'image_path': placeholder_path, 'prod_name': 'Coming Soon'}] * 5
            item_row = ImageRow("Recommendations", placeholder_data)
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