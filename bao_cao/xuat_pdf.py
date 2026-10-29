"""Mở .docx bằng Microsoft Word, cập nhật mục lục, lưu lại và xuất PDF.
Dùng:  python bao_cao/xuat_pdf.py <file.docx|file.pptx> [thư_mục_ảnh_xem_trước]"""
import os
import sys

import win32com.client

src = os.path.abspath(sys.argv[1])
pdf = os.path.splitext(src)[0] + ".pdf"

if src.endswith(".docx"):
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(src)
        for toc in d.TablesOfContents:
            toc.Update()
        d.Fields.Update()
        d.Save()
        d.ExportAsFixedFormat(pdf, 17)  # wdExportFormatPDF
        d.Close(False)
    finally:
        try:
            word.Quit()
        except Exception:  # WPS Office đăng ký COM "Word.Application" nhưng Quit không ổn định
            pass
else:
    pp = win32com.client.DispatchEx("PowerPoint.Application")
    try:
        pres = pp.Presentations.Open(src, WithWindow=False)
        pres.SaveAs(pdf, 32)  # ppSaveAsPDF
        pres.Close()
    finally:
        try:
            pp.Quit()
        except Exception:
            pass
print("pdf:", pdf)

if len(sys.argv) > 2:
    import fitz
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    with fitz.open(pdf) as f:
        for i, page in enumerate(f, 1):
            page.get_pixmap(dpi=60).save(os.path.join(out, f"p{i:02d}.png"))
        print("pages:", len(f))
