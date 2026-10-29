"""Kịch bản demo: luồng bình thường và các tình huống tấn công/giả mạo.

Mỗi kịch bản chạy trên một môi trường mới và trả về danh sách bước (mô tả, kết quả, chi tiết).
"""
from .core import PolicyError
from .seed import DemoEnv

HOUR = 3600


class Recorder:
    def __init__(self):
        self.steps = []

    def ok(self, step, detail=""):
        self.steps.append({"step": step, "result": "THÀNH CÔNG", "detail": detail})

    def detect(self, step, detail=""):
        self.steps.append({"step": step, "result": "PHÁT HIỆN", "detail": detail})

    def info(self, step, detail=""):
        self.steps.append({"step": step, "result": "THÔNG TIN", "detail": detail})

    def expect_block(self, step, fn):
        try:
            fn()
        except PolicyError as e:
            self.steps.append({"step": step, "result": "BỊ CHẶN", "detail": f"{e.code}: {e.message}"})
            return e
        self.steps.append({"step": step, "result": "KHÔNG CHẶN (LỖI!)", "detail": ""})
        return None


def _vnd(x):
    return f"{x:,}".replace(",", ".") + " đ"


def s01_normal_small(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 40_000_000,
                                 "Thanh toán hoá đơn bao bì tháng 10 (HĐ 0001234)")
    r.ok("Kế toán tạo lệnh 40 triệu cho nhà cung cấp quen", f"Rủi ro {req.risk['level']} ({req.risk['score']}), cần {req.required_approvals} người duyệt")
    ktt = env.login("ketoantruong")
    env.approve(ktt, req.id)
    r.ok("Kế toán trưởng xem nội dung trên điện thoại và ký duyệt", f"Trạng thái: {req.status}")
    env.svc.execute_payment(kt, req.id)
    r.ok("Lệnh được gửi sang ngân hàng", f"Mã giao dịch {req.bank_ref}")


def s02_normal_large(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    ktt = env.login("ketoantruong")
    gd = env.login("giamdoc")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 120_000_000,
                                 "Đặt cọc đơn hàng bao bì quý 4")
    r.ok("Tạo lệnh 120 triệu", f"Rủi ro {req.risk['level']}, cần {req.required_approvals} người duyệt")
    env.approve(ktt, req.id)
    r.info("Kế toán trưởng duyệt – chưa đủ", "; ".join(env.svc.approval_gaps(req.id)))
    env.approve(gd, req.id)
    env.svc.execute_payment(kt, req.id)
    r.ok("Giám đốc duyệt → lệnh được thực thi", f"Mã giao dịch {req.bank_ref}")


def s03_deepfake_new_account(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    r.info("Kế toán nhận cuộc gọi video 'Giám đốc Lê Hoàng Nam' (deepfake): chuyển gấp 850 triệu đặt cọc dự án mật, STK 9704 2299 8811",
           "Hình ảnh và giọng nói giống thật – hệ thống KHÔNG dựa vào đó")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Phần mềm An Tâm"], 850_000_000,
                                 "Đặt cọc gấp dự án bí mật theo chỉ đạo của Giám đốc", source_channel="VIDEO_CALL",
                                 claimed_by_username="giamdoc", urgent=True, account_no_in_message="970422998811")
    r.ok("Hệ thống chấm điểm rủi ro", f"Trạng thái {req.status}: " + "; ".join(req.risk["block_reasons"]))


def s04_deepfake_existing_vendor(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Phần mềm An Tâm"], 300_000_000,
                                 "Thanh toán gấp bản quyền phần mềm – Giám đốc yêu cầu giữ kín",
                                 source_channel="VOICE_CALL", claimed_by_username="giamdoc", urgent=True)
    r.ok("Kẻ gian giả giọng Giám đốc, yêu cầu chuyển 300 triệu cho NCC có trong sổ",
         f"Rủi ro {req.risk['level']} ({req.risk['score']} điểm). Điều kiện: " + "; ".join(env.svc.approval_gaps(req.id)))
    ktt = env.login("ketoantruong")
    env.approve(ktt, req.id)
    r.expect_block("Kế toán thử thực thi khi mới có Kế toán trưởng duyệt", lambda: env.svc.execute_payment(kt, req.id))
    r.expect_block("Kế toán trưởng gọi lại số do 'Giám đốc' đọc trong cuộc gọi (0988 777 666)",
                   lambda: env.svc.record_payment_callback(ktt, req.id, "0988 777 666", True))
    env.svc.record_payment_callback(ktt, req.id, "0901 000 003", False, "GĐ đang họp, xác nhận không hề gọi")
    r.ok("Gọi lại số của Giám đốc trong danh bạ nội bộ → GĐ xác nhận không yêu cầu", f"Trạng thái lệnh: {req.status}")


def s05_bec_vendor_email(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    bid = env.bene["Công ty TNHH Bao Bì Minh Phát"]
    c = env.svc.request_account_change(kt, bid, "ACB", "88886666999", "EMAIL",
                                       "Email từ minhphat-packaging.co (giả mạo): 'Do kiểm toán, từ tháng này vui lòng chuyển vào TK mới. LH: 0912 345 678'")
    r.ok("Nhận email 'đổi số tài khoản' từ nhà cung cấp", f"Yêu cầu {c.id} ở trạng thái {c.status} – STK cũ vẫn giữ nguyên")
    ktt = env.login("ketoantruong")
    r.expect_block("Gọi lại số điện thoại ghi trong email", lambda: env.svc.record_change_callback(ktt, c.id, "0912 345 678", True))
    env.svc.record_change_callback(ktt, c.id, "028 3812 3456", False, "NCC xác nhận không đổi tài khoản")
    r.ok("Gọi lại số trong sổ đăng ký → NCC xác nhận không gửi email", f"Yêu cầu đổi STK: {c.status}")
    r.expect_block("Kẻ gian thúc giục duyệt đổi STK", lambda: env.approve_change(ktt, c.id))
    r.info("Số tài khoản trong sổ vẫn là", env.svc.beneficiaries[bid].account_no)


def s06_legit_account_change(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    bid = env.bene["Công ty CP Vận tải Sao Việt"]
    c = env.svc.request_account_change(kt, bid, "Vietinbank", "108866554433", "EMAIL", "NCC chuyển ngân hàng giao dịch")
    ktt = env.login("ketoantruong")
    env.svc.record_change_callback(ktt, c.id, "028 3999 1122", True, "Đã xác nhận với kế toán trưởng NCC")
    env.approve_change(ktt, c.id)
    r.ok("Đổi STK hợp lệ: gọi lại đúng số + Kế toán trưởng ký duyệt", f"Thời gian chờ an toàn 48 giờ bắt đầu")
    req = env.svc.create_payment(kt, bid, 14_000_000, "Cước vận chuyển tháng 11")
    r.ok("Tạo lệnh ngay sau khi đổi STK", f"Trạng thái {req.status}: " + "; ".join(req.risk["block_reasons"]))
    env.clock.advance(49 * HOUR)
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, bid, 14_000_000, "Cước vận chuyển tháng 11")
    r.ok("Sau 49 giờ tạo lại lệnh", f"Rủi ro {req.risk['level']} ({req.risk['score']}): cần {req.required_approvals} người duyệt")


def s07_password_guessing(env: DemoEnv, r: Recorder):
    for i in range(5):
        env.clock.advance(31)
        ch, sig = env.wallet.sign_login(env.svc, "ketoantruong", "ketoantruong-phone")
        r.expect_block(f"Lần {i + 1}: đúng mật khẩu (bị lộ) nhưng đoán OTP",
                       lambda: env.svc.login("ketoantruong", env.passwords["ketoantruong"], "123456", "ketoantruong-phone", sig))
    r.expect_block("Lần 6: dù có đủ thông tin cũng bị từ chối do tài khoản tạm khoá",
                   lambda: env.login("ketoantruong"))


def s08_phished_credentials(env: DemoEnv, r: Recorder):
    pk = env.wallet.create("attacker-laptop", "attacker", "Laptop kẻ tấn công")
    otp = env.otp("ketoantruong")
    r.expect_block("Kẻ gian lừa lấy được mật khẩu + OTP (trang giả mạo), đăng nhập từ máy của mình",
                   lambda: env.login("ketoantruong", device_id="attacker-laptop", otp=otp))
    env.clock.advance(31)
    d = env.svc.request_device_enrollment("ketoantruong", env.passwords["ketoantruong"], env.otp("ketoantruong"),
                                          "attacker-laptop", pk, "Laptop mới")
    r.ok("Kẻ gian đăng ký 'thiết bị mới'", f"Thiết bị ở trạng thái {d.status}, chủ tài khoản nhận cảnh báo")
    r.expect_block("Đăng nhập bằng thiết bị đang chờ duyệt", lambda: env.login("ketoantruong", device_id="attacker-laptop"))


def s09_stolen_session(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 45_000_000, "Hoá đơn bao bì")
    ktt_token = env.login("ketoantruong")
    env.wallet.create("attacker-laptop", "attacker", "Laptop kẻ tấn công")
    forged = env.wallet.sign_payment(env.svc, req.id, "attacker-laptop", "APPROVE")
    r.expect_block("Kẻ gian đánh cắp cookie phiên của Kế toán trưởng, ký duyệt bằng khoá của mình",
                   lambda: env.svc.decide_payment(ktt_token, req.id, "APPROVE", forged))


def s10_swapped_content(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 48_000_000, "Hoá đơn bao bì")
    ktt = env.login("ketoantruong")
    r.expect_block("Mã độc trên trình duyệt sửa số tiền hiển thị thành 4.800.000 đ để lừa người duyệt ký",
                   lambda: env.approve(ktt, req.id, amount=4_800_000))


def s11_db_tampering(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 44_000_000, "Hoá đơn bao bì")
    ktt = env.login("ketoantruong")
    env.approve(ktt, req.id)
    req.account_no = "970422998811"
    r.info("Kẻ nội gián sửa trực tiếp STK của lệnh đã duyệt trong CSDL", req.account_no)
    r.expect_block("Thực thi lệnh", lambda: env.svc.execute_payment(kt, req.id))


def s12_self_approval(env: DemoEnv, r: Recorder):
    ktt = env.login("ketoantruong")
    req = env.svc.create_payment(ktt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 20_000_000, "Tạm ứng")
    r.expect_block("Kế toán trưởng tự tạo rồi tự duyệt lệnh", lambda: env.approve(ktt, req.id))


def s13_compromised_approver(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, env.bene["Công ty TNHH Bao Bì Minh Phát"], 49_000_000, "Hoá đơn bao bì")
    ktt = env.login("ketoantruong")
    env.approve(ktt, req.id)
    r.info("Điện thoại của Kế toán trưởng bị chiếm và đã ký duyệt 1 lệnh", f"Trạng thái {req.status}")
    admin = env.login("admin")
    res = env.svc.report_compromise(admin, env.user_ids["ketoantruong"])
    r.ok("Kế toán trưởng gọi hotline, quản trị viên kích hoạt khoá khẩn cấp",
         f"Thu hồi {res['devices']}, huỷ duyệt các lệnh {res['requests_reopened']}")
    r.expect_block("Phiên cũ của thiết bị bị chiếm tiếp tục thao tác", lambda: env.svc.session_info(ktt))
    r.expect_block("Thực thi lệnh đã duyệt trước đó", lambda: env.svc.execute_payment(kt, req.id))


def s14_audit_tampering(env: DemoEnv, r: Recorder):
    s01_normal_small(env, Recorder())
    anchor = env.svc.audit.anchor()
    log = env.svc.audit
    ok, _ = log.verify(anchor)
    r.info("Kiểm tra nhật ký ban đầu", "Toàn vẹn" if ok else "Lỗi")
    executed = next(e for e in log.entries if e["event"] == "PAYMENT_EXECUTED")
    executed["details"]["account_no"] = "970422998811"
    ok, problems = log.verify(anchor)
    r.detect("Sửa STK trong bản ghi nhật ký để che dấu vết", "Phát hiện: " + "; ".join(problems))
    executed["details"]["account_no"] = env.svc.requests["PR-0001"].account_no
    del log.entries[-3:]
    ok, problems = log.verify(anchor)
    r.detect("Xoá 3 bản ghi cuối nhật ký", "Phát hiện nhờ mốc neo bên ngoài: " + "; ".join(problems))


def s15_forged_images(env: DemoEnv, r: Recorder):
    kt = env.login("ketoan")
    bid = env.bene["Công ty TNHH Bao Bì Minh Phát"]
    r.info("Kế toán nhận qua Zalo ảnh chụp hoá đơn của Minh Phát – STK trên ảnh đã bị chỉnh sửa thành 0071000999888",
           "Ảnh trông như hoá đơn thật – hệ thống KHÔNG đọc STK từ ảnh")
    req = env.svc.create_payment(kt, bid, 45_000_000, "Thanh toán theo ảnh hoá đơn HĐ 0001240", "IMAGE",
                                 account_no_in_message="0071000999888")
    r.ok("Nhập STK trên ảnh để đối chiếu", f"Trạng thái {req.status}: " + "; ".join(req.risk["block_reasons"]))
    req = env.svc.create_payment(kt, bid, 45_000_000, "Ảnh chụp tin nhắn: 'Giám đốc đã duyệt, chuyển luôn'",
                                 "IMAGE", "giamdoc")
    r.ok("Kẻ gian gửi ảnh chụp màn hình 'Giám đốc đã duyệt' để hối thúc",
         f"Rủi ro {req.risk['level']} ({req.risk['score']}). Điều kiện: " + "; ".join(env.svc.approval_gaps(req.id)))
    ktt = env.login("ketoantruong")
    env.approve(ktt, req.id)
    r.expect_block("Kế toán trưởng duyệt rồi thực thi, coi ảnh chụp như chữ ký của Giám đốc",
                   lambda: env.svc.execute_payment(kt, req.id))


SCENARIOS = [
    ("KB01", "Luồng bình thường: lệnh nhỏ, 1 người duyệt", s01_normal_small),
    ("KB02", "Luồng bình thường: lệnh 120 triệu, 2 người duyệt", s02_normal_large),
    ("KB03", "Deepfake video Giám đốc + số tài khoản lạ", s03_deepfake_new_account),
    ("KB04", "Giả giọng Giám đốc, chuyển cho NCC có sẵn", s04_deepfake_existing_vendor),
    ("KB05", "Email giả nhà cung cấp đổi số tài khoản (BEC)", s05_bec_vendor_email),
    ("KB06", "Đổi số tài khoản hợp lệ + thời gian chờ 48h", s06_legit_account_change),
    ("KB07", "Lộ mật khẩu, dò mã OTP", s07_password_guessing),
    ("KB08", "Bị lừa lấy mật khẩu + OTP (phishing)", s08_phished_credentials),
    ("KB09", "Đánh cắp phiên đăng nhập (session hijacking)", s09_stolen_session),
    ("KB10", "Tráo nội dung lúc ký (mã độc/MITM)", s10_swapped_content),
    ("KB11", "Sửa dữ liệu trong CSDL sau khi duyệt", s11_db_tampering),
    ("KB12", "Tự tạo – tự duyệt", s12_self_approval),
    ("KB13", "Thiết bị người duyệt bị chiếm → khoá khẩn cấp", s13_compromised_approver),
    ("KB14", "Sửa / xoá nhật ký kiểm toán", s14_audit_tampering),
    ("KB15", "Ảnh hoá đơn bị sửa STK, ảnh chụp màn hình 'đã duyệt' giả", s15_forged_images),
]


def run_scenario(fn) -> list[dict]:
    env = DemoEnv()
    rec = Recorder()
    fn(env, rec)
    return rec.steps


def run_all() -> list[dict]:
    return [{"id": sid, "title": title, "steps": run_scenario(fn)} for sid, title, fn in SCENARIOS]
