from setuptools import setup, find_packages

setup(
    name="pdf_translator",
    version="0.1.0",
    description="PDF Translator CLI/GUI",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "PySide6==6.6.2",
        "click==8.1.7",
        "python-dotenv==1.0.0",
        "openai==0.27.6",
        "pdfplumber==0.9.0",
        "PyMuPDF==1.23.6"
    ],
)