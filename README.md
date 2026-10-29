# Đồ án cuối kỳ – Hướng 1 (Security): SafePay Guard

Hệ thống xác minh và phê duyệt lệnh chuyển tiền chống giả mạo (deepfake, BEC) cho doanh nghiệp vừa và nhỏ.

## Sản phẩm nộp

| Yêu cầu của đề | Tệp |
|---|---|
| Báo cáo đồ án | `BaoCao_DoAn_Huong1_SafePayGuard.docx` (+ bản `.pdf`) |
| Sơ đồ kiến trúc và các sơ đồ cần thiết | `so_do/*.png` (kiến trúc, luồng phê duyệt, quyết định tin cậy, đổi STK, ma trận rủi ro, phòng thủ nhiều lớp) |
| Prototype / source code | `prototype/` |
| Bộ test case và kết quả kiểm thử | `prototype/tests/test_safepay.py`, `ket_qua_kiem_thu/` |
| Slide thuyết trình và demo | `Slide_DoAn_Huong1_SafePayGuard.pptx` (+ bản `.pdf`, có ghi chú cho người nói) |
| Kịch bản thuyết trình 5 phút | `KichBan_ThuyetTrinh_5phut.docx` (+ bản `.pdf`, nguồn `slide/KichBan_ThuyetTrinh_5phut.md`) |

## Chạy prototype

```bash
pip install flask cryptography argon2-cffi pytest
cd prototype
python demo_cli.py        # 15 kịch bản demo trên terminal
python -m pytest -v       # 33 test case / 38 lượt chạy
python app.py             # giao diện web tại http://127.0.0.1:5000
```

Tài khoản demo (mật khẩu, OTP hiện tại) hiển thị ngay trên trang đăng nhập.

## Sinh lại tài liệu

```bash
python so_do/ve_so_do.py          # vẽ lại sơ đồ
python bao_cao/tao_bao_cao.py     # sinh lại báo cáo .docx
python slide/tao_slide.py         # sinh lại slide .pptx
python slide/tao_kich_ban_docx.py # sinh lại kịch bản thuyết trình .docx
python bao_cao/xuat_pdf.py <file.docx|file.pptx>   # xuất PDF (cần Word/WPS hoặc PowerPoint trên Windows)
```

Trước khi nộp, điền tên trường, khoa, thành viên nhóm và giảng viên hướng dẫn trên trang bìa báo cáo và slide 1.
