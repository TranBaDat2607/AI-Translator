import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSplitter,
    QFileDialog
)
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

        # --- Top bar: language selector, Open, Zoom In/Out ---
        top_bar = QHBoxLayout()
        vbox.addLayout(top_bar)

        top_bar.addWidget(QLabel("Target language:"))
        self.lang_combo = QComboBox()
        # Bạn có thể bổ sung danh sách ngôn ngữ tùy ý
        self.lang_combo.addItems(["Chinese", "English", "Japanese", "Vietnamese"])
        top_bar.addWidget(self.lang_combo)

        top_bar.addStretch()

        self.open_btn = QPushButton("Open PDF")
        self.open_btn.clicked.connect(self.open_pdf)
        top_bar.addWidget(self.open_btn)

        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        top_bar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        top_bar.addWidget(self.zoom_out_btn)

        # Translate button
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.clicked.connect(self.on_translate)
        top_bar.addWidget(self.translate_btn)

        # --- Splitter: left = original PDF, right = translated PDF (hiện là gốc) ---
        splitter = QSplitter(Qt.Horizontal)
        vbox.addWidget(splitter)

        # 1 QPdfDocument chia sẻ cho cả 2 view
        self.doc = QPdfDocument(self)
        # translated PDF document
        self.translated_doc = QPdfDocument(self)

        # left side: label + PDF
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

        # right side: label + PDF
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

        # update label while scroll 
        nav_left = self.left_view.pageNavigator()
        nav_left.currentPageChanged.connect(self.on_left_page_changed)
        nav_right = self.right_view.pageNavigator()
        nav_right.currentPageChanged.connect(self.on_right_page_changed)


        # khởi tạo zoom factor
        self.zoom_factor = 1.0

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

    def on_translate(self) -> None:
        """
        Handle Translate button click: perform translation and load result.
        """
        if not hasattr(self, "current_pdf_path"):
            QMessageBox.warning(self, "No PDF Loaded", "Please open a PDF before translating.")
            return
        lang = self.lang_combo.currentText()
        input_pdf = self.current_pdf_path
        base, _ = os.path.splitext(input_pdf)
        output_pdf = base + f"_{lang}.pdf"
        # perform translation
        convert_pdf(input_pdf, output_pdf, target_lang=lang)
        # load translated PDF into right view
        self.translated_doc.load(output_pdf)
        # reset zoom and update label
        self.zoom_factor = 1.0
        self.right_view.setZoomFactor(self.zoom_factor)
        total = self.translated_doc.pageCount()
        if total > 0:
            self.right_page_label.setText(f"1/{total}")
        else:
            self.right_page_label.setText("0/0")


if __name__ == "__main__":
    # Đảm bảo bạn đã pip install PySide6
    app = QApplication(sys.argv)
    win = PdfTranslatorUI()
    win.show()
    sys.exit(app.exec())