import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSplitter,
    QFileDialog, QMessageBox, QLineEdit
)
from PySide6.QtGui import QFontDatabase
import pathlib
from PySide6.QtCore import Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from pdf2zh.core import convert_pdf


class PdfTranslatorUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Translator")
        self.resize(1200, 800)

        # central container
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)

        # setup UI components
        self._setup_top_bar(vbox)
        self._setup_pdf_views(vbox)
        self._connect_signals()

        # initialize zoom factor
        self.zoom_factor = 1.0

    def _setup_top_bar(self, vbox):
        # --- Top bar: language selector, Open, Zoom In/Out ---
        top_bar = QHBoxLayout()
        vbox.addLayout(top_bar)

        top_bar.addWidget(QLabel("Service:"))
        self.service_combo = QComboBox()
        self.service_combo.addItems(["OpenAI", "Gemini"])
        top_bar.addWidget(self.service_combo)

        top_bar.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("Enter API Key")
        top_bar.addWidget(self.api_key_edit)


        top_bar.addWidget(QLabel("Target language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Chinese", "English", "Japanese", "Vietnamese"])
        top_bar.addWidget(self.lang_combo)

        top_bar.addStretch()

        self.open_btn = QPushButton("Open PDF")
        top_bar.addWidget(self.open_btn)

        self.zoom_in_btn = QPushButton("Zoom In")
        top_bar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Zoom Out")
        top_bar.addWidget(self.zoom_out_btn)

        self.translate_btn = QPushButton("Translate")
        top_bar.addWidget(self.translate_btn)

    def _setup_pdf_views(self, vbox):
        splitter = QSplitter(Qt.Horizontal)
        vbox.addWidget(splitter)

        self.doc = QPdfDocument(self)
        self.translated_doc = QPdfDocument(self)

        container_left = QWidget()
        layout_left = QVBoxLayout(container_left)
        layout_left.setContentsMargins(0, 0, 0, 0)
        self.left_page_label = QLabel("0/0")
        self.left_page_label.setAlignment(Qt.AlignCenter)
        layout_left.addWidget(self.left_page_label)

        self.left_view = QPdfView()
        self.left_view.setDocument(self.doc)
        self.left_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.left_view.setPageSpacing(8)
        layout_left.addWidget(self.left_view)
        splitter.addWidget(container_left)

        container_right = QWidget()
        layout_right = QVBoxLayout(container_right)
        layout_right.setContentsMargins(0, 0, 0, 0)
        self.right_page_label = QLabel("0/0")
        self.right_page_label.setAlignment(Qt.AlignCenter)
        layout_right.addWidget(self.right_page_label)

        self.right_view = QPdfView()
        self.right_view.setDocument(self.translated_doc)
        self.right_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.right_view.setPageSpacing(8)
        layout_right.addWidget(self.right_view)
        splitter.addWidget(container_right)

    def _connect_signals(self):
        # update placeholder when service changes
        self.service_combo.currentTextChanged.connect(self.on_service_changed)
        # button signals
        self.open_btn.clicked.connect(self.open_pdf)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.translate_btn.clicked.connect(self.on_translate)
        # page navigation signals
        nav_left = self.left_view.pageNavigator()
        nav_left.currentPageChanged.connect(self.on_left_page_changed)
        nav_right = self.right_view.pageNavigator()
        nav_right.currentPageChanged.connect(self.on_right_page_changed)


    def open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        # store current PDF path
        self.current_pdf_path = path
        # load PDF into original document
        self.doc.load(path)
        # reset zoom
        self.zoom_factor = 1.0
        self.left_view.setZoomFactor(self.zoom_factor)
        self.right_view.setZoomFactor(self.zoom_factor)

        # after loaded: update label 1/total
        total = self.doc.pageCount()
        if total > 0:
            self.left_page_label.setText(f"1/{total}")
            self.right_page_label.setText(f"1/{total}")
        else:
            self.left_page_label.setText("0/0")
            self.right_page_label.setText("0/0")

    def zoom_in(self) -> None:
        self.zoom_factor += 0.1
        self.left_view.setZoomFactor(self.zoom_factor)
        self.right_view.setZoomFactor(self.zoom_factor)

    def zoom_out(self) -> None:
        self.zoom_factor = max(0.1, self.zoom_factor - 0.1)
        self.left_view.setZoomFactor(self.zoom_factor)
        self.right_view.setZoomFactor(self.zoom_factor)

    # page change handlers
    def on_left_page_changed(self, page: int):
        total = self.doc.pageCount()
        self.left_page_label.setText(f"{page + 1}/{total}")
    
    def on_right_page_changed(self, page: int):
        total = self.doc.pageCount()
        self.right_page_label.setText(f"{page + 1}/{total}")

    def on_service_changed(self, service: str) -> None:
        """
        Clear API key field and update its placeholder when user switches service
        """
        self.api_key_edit.clear()
        self.api_key_edit.setPlaceholderText(f"Enter {service} API key")

    def on_translate(self) -> None:
        """
        Handle Translate button click: perform translation and load result.
        """
        if not hasattr(self, "current_pdf_path"):
            QMessageBox.warning(self, "No PDF Loaded", "Please open a PDF before translating.")
            return
        
        service = self.service_combo.currentText()
        lang = self.lang_combo.currentText()
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter API key.")
            return
        input_pdf = self.current_pdf_path
        base, _ = os.path.splitext(input_pdf)
        output_pdf = f"{base}_{service}_{lang}.pdf"

        convert_pdf(
            input_pdf=input_pdf,
            output_pdf=output_pdf,
            target_lang=lang,
            api_key=api_key,
        )

        # Load translated PDF file directly
        self.translated_doc.load(output_pdf)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Đăng ký NotoSans-Regular.ttf để Qt PDF viewer dùng đúng glyph tiếng Việt
    font_path = pathlib.Path(__file__).parent.parent / "src" / "pdf2zh" / "fonts" / "NotoSans-Regular.ttf"
    fid = QFontDatabase.addApplicationFont(str(font_path))
    if fid < 0:
        print("⚠️ Không load được font NotoSans-Regular.ttf")
    else:
        print(f"✅ Đã đăng ký NotoSans vào Qt (id={fid})")

    win = PdfTranslatorUI()
    win.show()
    sys.exit(app.exec())