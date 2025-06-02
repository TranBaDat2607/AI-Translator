from setuptools import setup, find_packages

setup(
    name="pdf_translator",
    version="0.1.0",
    description="PDF Translator CLI/GUI",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "PySide6>=6.6.2",
        "click>=8.1.7",
        "python-dotenv>=1.0.0",
        "openai>=0.27.6",
        "pdfplumber>=0.9.0,<0.13.0",       
        "PyMuPDF>=1.23.6",
        "pdfminer.six>=20221105,<20250416",
        "tqdm>=4.0",
        "tenacity>=8.0",
        "numpy>=1.22",
        "pikepdf>=6.0",
        "babeldoc>=0.1.22,<0.3.0",
        "requests>=2.28.0",
    ],
) 