"""Vẽ các sơ đồ cho báo cáo/slide.   Chạy:  python so_do/ve_so_do.py"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

plt.rcParams["font.family"] = ["Segoe UI", "Arial", "DejaVu Sans"]
OUT = os.path.dirname(os.path.abspath(__file__))

INK = "#1d2433"
BLUE, GREEN, RED, AMBER, GREY = "#1f4e8c", "#127a45", "#b42318", "#9a6700", "#667085"
Z_RED, Z_AMB, Z_BLUE, Z_GREEN = "#fdeeee", "#fff7e0", "#eaf1fb", "#e8f6ee"


def canvas(w, h, xmax=100, ymax=60):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def zone(ax, x, y, w, h, title, fc, ec):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.4, ls=(0, (5, 3))))
    ax.text(x + 0.8, y + h - 0.8, title, ha="left", va="top", fontsize=10, color=ec, weight="bold")


def box(ax, x, y, w, h, text, ec=BLUE, fc="white", fs=9, bold_first=True, tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=fc, ec=ec, lw=1.5))
    lines = text.split("\n")
    if bold_first and len(lines) > 1:
        n = len(lines) - 1  # hai lớp chữ cùng số dòng để căn thẳng hàng
        ax.text(x + w / 2, y + h / 2, "\n".join([lines[0]] + [" "] * n), ha="center", va="center", fontsize=fs,
                weight="bold", color=tc, linespacing=1.3)
        ax.text(x + w / 2, y + h / 2, "\n".join([" "] + lines[1:]), ha="center", va="center", fontsize=fs,
                color=tc, linespacing=1.3)
    else:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc,
                weight="bold" if bold_first else "normal")


def diamond(ax, cx, cy, w, h, text, ec=AMBER, fs=8.5):
    ax.add_patch(plt.Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                             fc="#fffaf0", ec=ec, lw=1.5))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=INK)


def arrow(ax, p1, p2, text="", color=GREY, fs=8, rad=0.0, off=(0, 0.8), ls="-", lw=1.3, ha="center"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=12, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))
    if text:
        mx, my = (p1[0] + p2[0]) / 2 + off[0], (p1[1] + p2[1]) / 2 + off[1]
        ax.text(mx, my, text, ha=ha, va="center", fontsize=fs, color=color,
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- 1. Kiến trúc
def architecture():
    fig, ax = canvas(15, 9, 100, 62)
    zone(ax, 0.5, 6, 19, 54, "VÙNG KHÔNG TIN CẬY", Z_RED, RED)
    zone(ax, 21.5, 6, 17, 54, "THIẾT BỊ NGƯỜI DÙNG", Z_AMB, AMBER)
    zone(ax, 40.5, 1, 41, 59, "MÁY CHỦ SAFEPAY GUARD (vùng tin cậy)", Z_BLUE, BLUE)
    zone(ax, 83.5, 6, 16, 54, "BÊN NGOÀI TIN CẬY", Z_GREEN, GREEN)

    box(ax, 2, 46, 16, 8, "Email / Zalo / Telegram\nyêu cầu chuyển tiền,\nđổi số tài khoản", RED)
    box(ax, 2, 34, 16, 8, "Cuộc gọi thoại / video\ncó thể là deepfake\ngiọng nói, khuôn mặt", RED)
    box(ax, 2, 22, 16, 8, "Kẻ tấn công\nphishing, đánh cắp phiên,\nmã độc trình duyệt", RED)
    box(ax, 2, 10, 16, 8, "Trang đăng nhập giả\nthu mật khẩu + OTP", RED)

    box(ax, 23, 42, 14, 11, "Trình duyệt web\nKế toán viên nhập lệnh,\nghi kênh nguồn và\nngười tự xưng", AMBER)
    box(ax, 23, 22, 14, 15, "Ứng dụng ký (điện thoại)\n• Khoá riêng Ed25519\n  (không rời thiết bị)\n• Authenticator TOTP\n• Hiển thị nội dung ký", AMBER)
    box(ax, 23, 10, 14, 8, "Người duyệt\nKTT / Giám đốc", AMBER)

    box(ax, 42, 49, 17, 7.5, "Web/API Gateway\nTLS 1.3, cookie HttpOnly\nSameSite, kiểm tra đầu vào", BLUE)
    box(ax, 62, 49, 18, 7.5, "Dịch vụ xác thực\nArgon2id + TOTP + challenge\nthiết bị, khoá tạm, hết phiên", BLUE)
    box(ax, 42, 37, 17, 8.5, "Bộ chấm điểm rủi ro\nkênh nguồn, người tự xưng,\nkhẩn cấp, NCC mới, STK đổi,\nsố tiền bất thường", BLUE)
    box(ax, 62, 37, 18, 8.5, "Bộ máy chính sách duyệt\nmaker–checker, ngưỡng tiền,\nbắt buộc GĐ, gọi lại\nngoài băng, hạn 24h", BLUE)
    box(ax, 42, 25.5, 17, 8, "Xác minh chữ ký\nEd25519 trên nội dung\nchuẩn hoá + nonce", BLUE)
    box(ax, 62, 25.5, 18, 8, "Bộ thực thi lệnh\nkiểm tra lại HMAC, chữ ký,\nSTK sổ đăng ký, hạn", BLUE)
    box(ax, 42, 14, 38, 7, "Nhật ký kiểm toán chống sửa đổi\nchuỗi băm SHA-256 + HMAC, mốc neo định kỳ\nghi mọi đăng nhập, từ chối, phê duyệt, cảnh báo", BLUE)
    box(ax, 42, 3, 12, 8, "CSDL\nngười dùng, khoá công\nkhai, lệnh + HMAC", GREY)
    box(ax, 55.5, 2.5, 13, 9, "Sổ đăng ký NCC\n& danh bạ nội bộ – nguồn\ntin cậy gốc cho rủi ro,\ngọi lại, thực thi", GREEN)
    box(ax, 70, 3, 10.5, 8, "Kho khoá\nHSM / KMS\nkhoá HMAC", GREY)

    box(ax, 85, 38, 13, 12, "Ngân hàng\nAPI / Internet\nBanking doanh\nnghiệp", GREEN)
    box(ax, 85, 18, 13, 12, "Lưu trữ WORM /\nKiểm toán viên\nnhận mốc neo\nnhật ký", GREEN)

    arrow(ax, (18, 50), (23, 48), "người nhận\nnhập tay", RED, 7.5, off=(0, 2.4))
    arrow(ax, (18, 38), (23, 45), "", RED)
    arrow(ax, (18, 26), (23, 30), "", RED, ls="--")
    arrow(ax, (37, 50), (42, 52.5), "HTTPS", BLUE, 7.5)
    arrow(ax, (37, 30), (42, 29.5), "chữ ký", BLUE, 7.5)
    arrow(ax, (30, 18), (30, 22), "", AMBER)
    arrow(ax, (59, 52.5), (62, 52.5), "", BLUE)
    arrow(ax, (50.5, 49), (50.5, 45.5), "", BLUE)
    arrow(ax, (59, 41), (62, 41), "", BLUE)
    arrow(ax, (71, 37), (71, 33.5), "", BLUE)
    arrow(ax, (59, 29.5), (62, 29.5), "", BLUE)
    arrow(ax, (80, 29.5), (85, 42), "lệnh đã kiểm\ntra lại", GREEN, 7.5, off=(0, 0))
    arrow(ax, (80, 17.5), (85, 23), "mốc neo", GREEN, 7.5, off=(0, 0))
    ax.text(57.5, 22.4, "", fontsize=7)
    ax.text(50, 0.2, "", fontsize=7)
    save(fig, "01_kien_truc_he_thong.png")


# ---------------------------------------------------------------- 2. Sequence
def sequence():
    fig, ax = canvas(15, 10.5, 100, 72)
    actors = [("Kế toán viên\n(trình duyệt)", 7), ("Máy chủ\nSafePay", 26), ("Bộ chấm\nrủi ro", 42),
              ("Điện thoại\nngười duyệt", 59), ("Người duyệt\nKTT / GĐ", 76), ("Ngân hàng", 93)]
    for name, x in actors:
        box(ax, x - 6.5, 66, 13, 5, name, BLUE, fs=9, bold_first=False)
        ax.plot([x, x], [-6, 66], color="#c3cad6", lw=1.2, ls=(0, (4, 3)))
    ax.set_ylim(-8, 72)
    X = {n.split("\n")[0]: x for n, x in actors}
    k, s, r, p, a, b = (X["Kế toán viên"], X["Máy chủ"], X["Bộ chấm"], X["Điện thoại"], X["Người duyệt"], X["Ngân hàng"])
    steps = [
        (k, s, "1. Tạo lệnh: NCC chọn từ sổ đăng ký, số tiền,\nkênh nguồn, người tự xưng, STK trong tin nhắn", BLUE),
        (s, r, "2. Đánh giá rủi ro", BLUE),
        (r, s, "3. Điểm + luật chặn (STK lạ, đang chờ 48h)", BLUE),
        (s, s, "4. STK lấy từ sổ đăng ký; sinh nonce, hạn 24h;\nHMAC toàn vẹn; xác định số người duyệt", BLUE),
        (s, p, "5. Gửi nội dung cần ký (push)", BLUE),
        (p, a, "6. Hiển thị đúng nội dung sẽ ký (WYSIWYS)", AMBER),
        (a, p, "7. Xác nhận bằng sinh trắc / PIN", AMBER),
        (p, s, "8. Chữ ký Ed25519(nội dung + nonce + quyết định)", AMBER),
        (s, s, "9. Xác minh chữ ký, tách biệt nhiệm vụ,\nhạn, chống phát lại, ghi nhật ký", BLUE),
        (a, s, "10. [Rủi ro cao] Gọi lại số trong danh bạ/sổ đăng ký,\nghi nhận kết quả", GREEN),
        (k, s, "11. Yêu cầu thực thi", BLUE),
        (s, s, "12. Kiểm tra LẠI: HMAC, mọi chữ ký,\nthiết bị còn hiệu lực, STK sổ đăng ký", RED),
        (s, b, "13. Gửi lệnh chuyển tiền", GREEN),
        (b, s, "14. Mã giao dịch → ghi nhật ký", GREEN),
    ]
    y = 62
    for src, dst, label, col in steps:
        if src == dst:
            ax.add_patch(FancyArrowPatch((src, y), (src, y - 2.6), arrowstyle="-|>", mutation_scale=11, color=col,
                                         lw=1.3, connectionstyle="arc3,rad=-1.6"))
            ax.text(src + 4.2, y - 1.3, label, ha="left", va="center", fontsize=8, color=col)
            y -= 6.4 if "\n" in label else 4.2
        else:
            arrow(ax, (src, y), (dst, y), "", col)
            ax.text((src + dst) / 2, y + 0.4, label, ha="center", va="bottom", fontsize=8, color=col,
                    bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85))
            y -= 5.2 if "\n" in label else 4.2
    save(fig, "02_luong_phe_duyet_lenh.png")


# ---------------------------------------------------------------- 3. Quyết định tin cậy
def trust_flow():
    fig, ax = canvas(15, 9.5, 100, 64)
    box(ax, 2, 52, 22, 9, "Thông tin đầu vào\nemail, chat, cuộc gọi thoại/video,\nhình ảnh hoá đơn, form web", RED)
    box(ax, 30, 52, 26, 9, "Coi là LỜI KHẲNG ĐỊNH CHƯA XÁC MINH\nkhông dùng STK / SĐT trong tin nhắn;\nchỉ lấy dữ liệu từ sổ đăng ký", AMBER)
    arrow(ax, (24, 56.5), (30, 56.5), "", GREY)
    diamond(ax, 74, 56.5, 22, 10, "STK trong tin nhắn\nkhác sổ đăng ký?")
    arrow(ax, (56, 56.5), (63, 56.5), "", GREY)
    box(ax, 88, 52, 11, 9, "CHẶN\ncảnh báo\nCRITICAL", RED, fc="#fdeeee")
    arrow(ax, (85, 56.5), (88, 56.5), "Có", RED, off=(0, 1.2))
    diamond(ax, 74, 42, 22, 10, "NCC vừa đổi STK\n(< 48 giờ)?")
    arrow(ax, (74, 51.5), (74, 47), "Không", GREY, off=(3, 0))
    arrow(ax, (85, 42), (93.5, 52), "Có", RED, off=(1, 0))
    box(ax, 30, 37.5, 26, 9, "Chấm điểm rủi ro\n+25 kênh ngoài · +20 tự xưng lãnh đạo\n+15 khẩn/bí mật · +20 NCC mới/số tiền lạ\n+30 STK đổi < 30 ngày · +10 ngoài giờ", BLUE)
    arrow(ax, (63, 42), (56, 42), "Không", GREY, off=(0, 1.2))
    box(ax, 2, 25, 17, 8, "THẤP (< 30)\n1 người duyệt\n(≥ 50tr: 2 người)", GREEN)
    box(ax, 21, 25, 17, 8, "TRUNG BÌNH (30–59)\n2 người duyệt", AMBER)
    box(ax, 40, 25, 20, 8, "CAO (≥ 60)\n2 người + Giám đốc\n+ gọi lại ngoài băng", RED)
    box(ax, 62, 25, 26, 8, "Có người TỰ XƯNG (vd 'Giám đốc')\nchính người đó phải ký trên thiết bị\nđã đăng ký + gọi lại số danh bạ", RED)
    for x in (10.5, 29.5, 50, 75):
        arrow(ax, (43, 37.5), (x, 33), "", GREY)
    box(ax, 18, 11, 30, 9, "Thu chữ ký Ed25519 từ thiết bị ACTIVE\nchữ ký phải khớp nội dung + nonce + quyết định;\nkhông tự duyệt; mỗi người 1 lần; hạn 24h", BLUE)
    for x in (10.5, 29.5, 50, 75):
        arrow(ax, (x, 25), (33, 20), "", GREY)
    box(ax, 56, 11, 30, 9, "Thực thi – KHÔNG tin trạng thái trong CSDL\nkiểm tra lại HMAC, mọi chữ ký,\nthiết bị chưa bị thu hồi, STK sổ đăng ký", GREEN)
    arrow(ax, (48, 15.5), (56, 15.5), "", GREY)
    ax.text(50, 4, "TIN: chữ ký từ thiết bị đã đăng ký · sổ đăng ký NCC & danh bạ đã xác minh · kết quả gọi lại số trong sổ\n"
                   "KHÔNG TIN: giọng nói, khuôn mặt, email, tin nhắn, số điện thoại/STK do người yêu cầu cung cấp, dữ liệu trình duyệt gửi lên",
            ha="center", va="center", fontsize=9, color=INK, bbox=dict(fc="#f4f6f9", ec="#c3cad6", pad=6))
    save(fig, "03_co_che_quyet_dinh_tin_cay.png")


# ---------------------------------------------------------------- 4. Đổi STK
def account_change():
    fig, ax = canvas(15, 6.2, 100, 40)
    box(ax, 1, 24, 15, 10, "Nhận yêu cầu\nđổi số tài khoản\n(email/chat/công văn)", RED)
    box(ax, 20, 24, 16, 10, "PENDING_CALLBACK\nSTK cũ giữ nguyên;\ncảnh báo người duyệt", AMBER)
    arrow(ax, (16, 29), (20, 29), "", GREY)
    box(ax, 40, 24, 18, 10, "Gọi lại số trong\nSỔ ĐĂNG KÝ\n(số trong thư → bị từ chối)", BLUE)
    arrow(ax, (36, 29), (40, 29), "", GREY)
    diamond(ax, 68, 29, 15, 10, "NCC xác\nnhận?")
    arrow(ax, (58, 29), (60.5, 29), "", GREY)
    box(ax, 80, 24, 19, 10, "REJECTED\ncảnh báo CRITICAL\n'nghi BEC'", RED, fc="#fdeeee")
    arrow(ax, (75.5, 29), (80, 29), "Không", RED, off=(0, 1.3))
    box(ax, 57, 5, 22, 10, "Người KHÁC người tiếp nhận\nký duyệt (Ed25519)\ntrên thiết bị đã đăng ký", BLUE)
    arrow(ax, (68, 24), (68, 15), "Có", GREEN, off=(2, 0))
    box(ax, 30, 5, 22, 10, "Áp dụng STK mới\n+ 48 giờ chờ an toàn\n(lệnh trong 48h bị chặn)", GREEN)
    arrow(ax, (57, 10), (52, 10), "", GREY)
    box(ax, 3, 5, 22, 10, "Sau 48h: thanh toán được\nnhưng rủi ro +30 trong 30 ngày\n→ tối thiểu 2 người duyệt", GREEN)
    arrow(ax, (30, 10), (25, 10), "", GREY)
    save(fig, "04_luong_doi_so_tai_khoan.png")


# ---------------------------------------------------------------- 5. Ma trận rủi ro
RISKS = [
    ("R1", "Giả danh lãnh đạo (deepfake/giả giọng)", 4, 5),
    ("R2", "Email giả NCC đổi số tài khoản (BEC)", 4, 5),
    ("R3", "Lộ mật khẩu / phishing lấy OTP", 4, 4),
    ("R4", "Đánh cắp phiên đăng nhập", 3, 4),
    ("R5", "Mã độc tráo nội dung khi duyệt", 2, 5),
    ("R6", "Nội gián sửa dữ liệu trong CSDL", 2, 5),
    ("R7", "Người tạo lệnh tự duyệt / thông đồng", 3, 4),
    ("R8", "Mất / bị chiếm điện thoại người duyệt", 3, 4),
    ("R9", "Phát lại chữ ký / OTP", 2, 3),
    ("R10", "Xoá / sửa nhật ký để che dấu vết", 2, 4),
]


def risk_matrix():
    import numpy as np
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 6.3), gridspec_kw={"width_ratios": [1, 1.05]})
    score = np.array([[l * i for l in range(1, 6)] for i in range(1, 6)])
    colors = np.where(score >= 15, 3, np.where(score >= 8, 2, np.where(score >= 4, 1, 0)))
    from matplotlib.colors import ListedColormap
    ax.imshow(colors, cmap=ListedColormap(["#e8f6ee", "#fff7e0", "#fde3c8", "#f8d0cc"]), origin="lower",
              extent=(0.5, 5.5, 0.5, 5.5))
    for x in range(1, 6):
        for y in range(1, 6):
            ax.add_patch(Rectangle((x - 0.5, y - 0.5), 1, 1, fill=False, ec="white", lw=2))
    cells = {}
    for rid, _, l, i in RISKS:
        cells.setdefault((l, i), []).append(rid)
    for (l, i), ids in cells.items():
        ax.text(l, i, "\n".join(ids), ha="center", va="center", fontsize=10, weight="bold", color=INK)
    ax.set_xticks(range(1, 6), ["Rất thấp", "Thấp", "Trung bình", "Cao", "Rất cao"])
    ax.set_yticks(range(1, 6), ["Rất nhỏ", "Nhỏ", "Trung bình", "Lớn", "Nghiêm trọng"])
    ax.set_xlabel("Khả năng xảy ra", fontsize=11)
    ax.set_ylabel("Mức độ thiệt hại", fontsize=11)
    ax.set_title("Ma trận rủi ro (trước khi áp dụng biện pháp)", fontsize=12, weight="bold")
    for s in ax.spines.values():
        s.set_visible(False)
    ax2.axis("off")
    rows = [[rid, desc, str(l), str(i), str(l * i)] for rid, desc, l, i in RISKS]
    t = ax2.table(cellText=rows, colLabels=["Mã", "Rủi ro", "KN", "TH", "Điểm"], loc="center",
                  colWidths=[0.08, 0.62, 0.08, 0.08, 0.1], cellLoc="left")
    t.auto_set_font_size(False)
    t.set_fontsize(9.5)
    t.scale(1, 1.75)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#d5dbe5")
        if r == 0:
            cell.set_facecolor("#1f4e8c")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        elif c == 4:
            v = int(rows[r - 1][4])
            cell.set_facecolor("#f8d0cc" if v >= 15 else "#fde3c8" if v >= 8 else "#fff7e0")
    save(fig, "05_ma_tran_rui_ro.png")


# ---------------------------------------------------------------- 6. Phòng thủ nhiều lớp khi bị chiếm tài khoản
def ato_layers():
    fig, ax = canvas(15, 6.6, 100, 44)
    steps = [
        ("Kẻ gian có\nMẬT KHẨU", "Bị chặn bởi OTP (TOTP)\n5 lần sai → khoá 15 phút", "TC07, TC08"),
        ("+ OTP\n(phishing thời gian thực)", "Bị chặn bởi challenge thiết bị\nOTP không dùng lại được", "TC09, TC10, TC12"),
        ("+ đăng ký\nTHIẾT BỊ MỚI", "PENDING – admin duyệt sau khi\nxác minh trực tiếp; chủ TK được báo", "TC11"),
        ("+ đánh cắp\nPHIÊN (cookie)", "Không có khoá riêng → không ký\nđược phê duyệt; phiên hết hạn 15'", "TC13, TC14"),
        ("+ chiếm điện thoại\n1 NGƯỜI DUYỆT", "Lệnh lớn/rủi ro cần người thứ 2 + GĐ\nkhoá khẩn cấp huỷ mọi chữ ký", "TC15, TC17"),
    ]
    w = 18.6
    for idx, (atk, defense, tc) in enumerate(steps):
        x = 1 + idx * (w + 1)
        h = 12 + idx * 4.5
        ax.add_patch(Rectangle((x, 2), w, h, fc="#eaf1fb", ec=BLUE, lw=1.4))
        ax.text(x + w / 2, 2 + h - 2.5, f"LỚP {idx + 1}", ha="center", fontsize=9, color=BLUE, weight="bold")
        ax.text(x + w / 2, 2 + h / 2 - 1, defense, ha="center", va="center", fontsize=8.6, color=INK)
        ax.text(x + w / 2, 3.6, tc, ha="center", fontsize=8, color=GREY)
        box(ax, x + 1, 2 + h + 2, w - 2, 6.5, atk, RED, fs=8.8, bold_first=False)
        arrow(ax, (x + w / 2, 2 + h + 2), (x + w / 2, 2 + h + 0.2), "", RED)
    ax.text(50, 43, "Mỗi lớp giả định lớp trước đã bị vượt qua (defense in depth)", ha="center", fontsize=11,
            weight="bold", color=INK)
    save(fig, "06_phong_thu_nhieu_lop.png")


if __name__ == "__main__":
    architecture()
    sequence()
    trust_flow()
    account_change()
    risk_matrix()
    ato_layers()
