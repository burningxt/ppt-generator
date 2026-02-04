from PyPDF2 import PdfReader
import sys


def check_pdf_size(pdf_path):
    reader = PdfReader(pdf_path)
    for i, page in enumerate(reader.pages):
        box = page.mediabox
        print(f"Page {i + 1}: {box.width} x {box.height}")


if __name__ == "__main__":
    check_pdf_size(sys.argv[1])
