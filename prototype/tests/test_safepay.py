"""Bộ test case SafePay Guard.

Docstring mỗi test có dạng:  Nhóm | Mô tả tình huống | Kết quả mong đợi
(được dùng để sinh bảng test case trong báo cáo).
"""
import pytest

from safepay.core import PolicyError
from safepay.crypto import DeviceKey, canonical

HOUR = 3600


def blocked(code, fn):
    with pytest.raises(PolicyError) as ei:
        fn()
    assert ei.value.code == code, f"mong đợi {code}, nhận {ei.value.code}: {ei.value.message}"
    return ei.value


# ===================== Luồng bình thường =====================
def test_tc01_login_ok(env):
    """Bình thường | Đăng nhập đúng mật khẩu + OTP từ thiết bị đã đăng ký | Đăng nhập thành công, tạo phiên gắn với thiết bị"""
    tok = env.login("ketoan")
    info = env.svc.session_info(tok)
    assert info["user"].username == "ketoan" and info["device_id"] == "ketoan-phone"


def test_tc02_small_payment(env, ids):
    """Bình thường | Lệnh 40 triệu cho nhà cung cấp quen, tạo trên hệ thống | Rủi ro LOW, 1 người duyệt, thực thi thành công"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 40_000_000, "Hoá đơn tháng 10")
    assert req.risk["level"] == "LOW" and req.required_approvals == 1
    env.approve(ktt, req.id)
    assert env.svc.execute_payment(kt, req.id).status == "EXECUTED"


def test_tc03_two_approvers(env, ids):
    """Bình thường | Lệnh 120 triệu | Cần 2 người duyệt; 1 người duyệt chưa thực thi được; đủ 2 người thì thực thi"""
    kt, ktt, gd = env.login("ketoan"), env.login("ketoantruong"), env.login("giamdoc")
    req = env.svc.create_payment(kt, ids["MP"], 120_000_000, "Đặt cọc quý 4")
    assert req.required_approvals == 2
    env.approve(ktt, req.id)
    blocked("CHUA_DU_PHE_DUYET", lambda: env.svc.execute_payment(kt, req.id))
    env.approve(gd, req.id)
    assert env.svc.execute_payment(kt, req.id).status == "EXECUTED"


def test_tc04_director_required(env, ids):
    """Bình thường | Lệnh 600 triệu (≥ 500 triệu) | Bắt buộc có chữ ký Giám đốc/Phó GĐ"""
    kt, ktt, gd = env.login("ketoan"), env.login("ketoantruong"), env.login("phogiamdoc")
    env.svc.beneficiaries[ids["MP"]].payment_history = [500_000_000]
    req = env.svc.create_payment(kt, ids["MP"], 600_000_000, "Mua nguyên liệu năm 2027")
    assert req.require_director
    env.approve(ktt, req.id)
    assert any("Giám đốc" in g for g in env.svc.approval_gaps(req.id))
    env.approve(gd, req.id)
    assert env.svc.execute_payment(kt, req.id).status == "EXECUTED"


def test_tc05_legit_account_change(env, ids):
    """Bình thường | NCC đổi STK thật: gọi lại đúng số trong sổ, Kế toán trưởng ký duyệt, chờ 48h | STK được cập nhật; sau 48h thanh toán được (rủi ro MEDIUM, 2 người duyệt)"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    c = env.svc.request_account_change(kt, ids["SV"], "Vietinbank", "108866554433", "EMAIL", "Đổi ngân hàng")
    env.svc.record_change_callback(ktt, c.id, "028 3999 1122", True)
    env.approve_change(ktt, c.id)
    assert env.svc.beneficiaries[ids["SV"]].account_no == "108866554433"
    env.clock.advance(49 * HOUR)
    kt, ktt, gd = env.login("ketoan"), env.login("ketoantruong"), env.login("giamdoc")
    req = env.svc.create_payment(kt, ids["SV"], 14_000_000, "Cước tháng 11")
    assert req.status == "PENDING_APPROVAL" and req.risk["level"] == "MEDIUM" and req.required_approvals == 2
    env.approve(ktt, req.id)
    env.approve(gd, req.id)
    assert env.svc.execute_payment(kt, req.id).account_no == "108866554433"


def test_tc06_reject(env, ids):
    """Bình thường | Người duyệt ký TỪ CHỐI | Lệnh chuyển REJECTED, không thể thực thi"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 30_000_000, "Hoá đơn")
    env.approve(ktt, req.id, "REJECT")
    assert req.status == "REJECTED"
    blocked("CHUA_DU_PHE_DUYET", lambda: env.svc.execute_payment(kt, req.id))


# ===================== Xác thực & chiếm quyền tài khoản =====================
def test_tc07_wrong_password(env):
    """Chiếm tài khoản | Sai mật khẩu | Từ chối với thông báo chung (không lộ tài khoản có tồn tại hay không)"""
    e1 = blocked("DANG_NHAP_THAT_BAI", lambda: env.login("ketoan", password="sai"))
    e2 = blocked("DANG_NHAP_THAT_BAI", lambda: env.login("khongtontai", device_id="ketoan-phone", password="x", otp="000000"))
    assert e1.message == e2.message


def test_tc08_otp_bruteforce_lockout(env):
    """Chiếm tài khoản | Lộ mật khẩu, kẻ gian đoán OTP 5 lần | Tài khoản bị khoá 15 phút, chủ tài khoản được cảnh báo; hết 15 phút đăng nhập lại được"""
    for _ in range(5):
        blocked("OTP_KHONG_HOP_LE", lambda: env.login("ketoantruong", otp="000000"))
    blocked("TAI_KHOAN_TAM_KHOA", lambda: env.login("ketoantruong"))
    assert any("bị khoá 15 phút" in n["message"] for n in env.svc.notifications)
    env.clock.advance(15 * 60)
    assert env.login("ketoantruong")


def test_tc09_otp_replay(env):
    """Chiếm tài khoản | Sử dụng sai ngữ cảnh – phát lại mã OTP vừa được dùng (bắt được qua trang giả mạo) | Từ chối OTP_DA_SU_DUNG"""
    otp = env.otp("ketoan")
    ch, sig = env.wallet.sign_login(env.svc, "ketoan", "ketoan-phone")
    env.svc.login("ketoan", env.passwords["ketoan"], otp, "ketoan-phone", sig)
    ch, sig = env.wallet.sign_login(env.svc, "ketoan", "ketoan-phone")
    blocked("OTP_DA_SU_DUNG", lambda: env.svc.login("ketoan", env.passwords["ketoan"], otp, "ketoan-phone", sig))


def test_tc10_phished_credentials_unknown_device(env):
    """Chiếm tài khoản | Kẻ gian có mật khẩu + OTP thật, đăng nhập từ máy của mình | Từ chối THIET_BI_CHUA_DANG_KY, cảnh báo chủ tài khoản"""
    env.wallet.create("attacker-pc", "attacker", "PC kẻ gian")
    blocked("THIET_BI_CHUA_DANG_KY", lambda: env.login("ketoantruong", device_id="attacker-pc"))
    assert any("thiết bị chưa được đăng ký" in n["message"] for n in env.svc.notifications)


def test_tc11_device_enrollment_needs_admin(env):
    """Chiếm tài khoản | Kẻ gian đăng ký 'thiết bị mới' bằng mật khẩu + OTP lộ | Thiết bị ở trạng thái PENDING, không đăng nhập được; admin không được tự duyệt thiết bị của mình"""
    pk = env.wallet.create("attacker-pc", "ketoantruong", "Laptop mới")
    d = env.svc.request_device_enrollment("ketoantruong", env.passwords["ketoantruong"], env.otp("ketoantruong"),
                                          "attacker-pc", pk, "Laptop mới")
    assert d.status == "PENDING"
    blocked("THIET_BI_CHUA_DANG_KY", lambda: env.login("ketoantruong", device_id="attacker-pc"))
    pk2 = env.wallet.create("admin-laptop", "admin", "Laptop admin")
    env.clock.advance(31)
    env.svc.request_device_enrollment("admin", env.passwords["admin"], env.otp("admin"), "admin-laptop", pk2, "x")
    adm = env.login("admin")
    blocked("TACH_BIET_NHIEM_VU", lambda: env.svc.approve_device(adm, "admin-laptop"))


def test_tc12_spoofed_device_id(env):
    """Chiếm tài khoản | Kẻ gian khai báo đúng mã thiết bị 'ketoan-phone' nhưng không có khoá riêng | Từ chối CHU_KY_KHONG_HOP_LE"""
    env.clock.advance(31)
    ch = env.svc.start_login("ketoan")
    fake = DeviceKey().sign(canonical(env.svc.login_payload("ketoan", ch, "ketoan-phone")))
    blocked("CHU_KY_KHONG_HOP_LE", lambda: env.svc.login("ketoan", env.passwords["ketoan"], env.otp("ketoan"), "ketoan-phone", fake))


def test_tc13_stolen_session(env, ids):
    """Chiếm tài khoản | Kẻ gian đánh cắp cookie phiên của Kế toán trưởng và gửi phê duyệt | Từ chối vì không có khoá riêng trên điện thoại người duyệt"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 45_000_000, "Hoá đơn")
    forged = DeviceKey().sign(canonical(env.svc.payment_payload(req, "APPROVE")))
    blocked("CHU_KY_KHONG_HOP_LE", lambda: env.svc.decide_payment(ktt, req.id, "APPROVE", forged))
    assert req.status == "PENDING_APPROVAL"


def test_tc14_session_idle_timeout(env):
    """Chiếm tài khoản | Dùng lại phiên bỏ quên sau 16 phút không hoạt động | Phiên hết hạn PHIEN_HET_HAN"""
    tok = env.login("ketoan")
    env.clock.advance(16 * 60)
    blocked("PHIEN_HET_HAN", lambda: env.svc.session_info(tok))


def test_tc15_emergency_lock(env, ids):
    """Chiếm tài khoản | Thiết bị Kế toán trưởng bị chiếm đã ký duyệt 1 lệnh; admin kích hoạt khoá khẩn cấp | Thu hồi thiết bị + phiên, phê duyệt bị huỷ, lệnh không thực thi được"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 49_000_000, "Hoá đơn")
    env.approve(ktt, req.id)
    assert req.status == "APPROVED"
    adm = env.login("admin")
    res = env.svc.report_compromise(adm, env.user_ids["ketoantruong"])
    assert res["requests_reopened"] == [req.id] and req.status == "PENDING_APPROVAL"
    blocked("PHIEN_KHONG_HOP_LE", lambda: env.svc.session_info(ktt))
    blocked("CHUA_DU_PHE_DUYET", lambda: env.svc.execute_payment(kt, req.id))
    blocked("THIET_BI_CHUA_DANG_KY", lambda: env.login("ketoantruong"))


# ===================== Thông tin đầu vào giả mạo =====================
def test_tc16_deepfake_unknown_account(env, ids):
    """Đầu vào giả mạo | Cuộc gọi video deepfake 'Giám đốc' yêu cầu chuyển gấp 850 triệu vào STK lạ | Lệnh bị CHẶN ngay (STK trong tin nhắn khác sổ đăng ký), cảnh báo CRITICAL"""
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, ids["AT"], 850_000_000, "Đặt cọc gấp, giữ kín", "VIDEO_CALL",
                                 "giamdoc", True, "970422998811")
    assert req.status == "BLOCKED" and req.risk["level"] == "CRITICAL"
    assert req.account_no == env.svc.beneficiaries[ids["AT"]].account_no  # không lấy STK từ tin nhắn
    assert any(a["level"] == "CRITICAL" for a in env.svc.alerts)


def test_tc17_deepfake_existing_vendor(env, ids):
    """Đầu vào giả mạo | Giả giọng Giám đốc yêu cầu chuyển 300 triệu cho NCC có sẵn | Rủi ro HIGH; KTT + Phó GĐ duyệt vẫn chưa đủ – phải có chính Giám đốc ký trên thiết bị và gọi lại xác minh"""
    kt, ktt, pgd = env.login("ketoan"), env.login("ketoantruong"), env.login("phogiamdoc")
    req = env.svc.create_payment(kt, ids["AT"], 300_000_000, "Bản quyền phần mềm gấp", "VOICE_CALL", "giamdoc", True)
    assert req.risk["level"] == "HIGH" and req.require_callback
    env.approve(ktt, req.id)
    env.approve(pgd, req.id)
    gaps = env.svc.approval_gaps(req.id)
    assert any("Lê Hoàng Nam" in g for g in gaps) and any("gọi lại" in g for g in gaps)
    blocked("CHUA_DU_PHE_DUYET", lambda: env.svc.execute_payment(kt, req.id))
    assert any(n["user_id"] == env.user_ids["giamdoc"] for n in env.svc.notifications)


def test_tc18_callback_to_attacker_number(env, ids):
    """Đầu vào giả mạo | Người duyệt gọi lại số điện thoại do kẻ gian đọc trong cuộc gọi | Từ chối SO_GOI_LAI_KHONG_HOP_LE – chỉ chấp nhận số trong danh bạ nội bộ"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["AT"], 300_000_000, "Gấp", "VOICE_CALL", "giamdoc", True)
    blocked("SO_GOI_LAI_KHONG_HOP_LE", lambda: env.svc.record_payment_callback(ktt, req.id, "0988 777 666", True))


def test_tc19_callback_denied(env, ids):
    """Đầu vào giả mạo | Gọi lại số thật của Giám đốc, GĐ xác nhận không hề yêu cầu | Lệnh REJECTED, cảnh báo nghi deepfake"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["AT"], 300_000_000, "Gấp", "VOICE_CALL", "giamdoc", True)
    env.svc.record_payment_callback(ktt, req.id, "0901000003", False, "GĐ không gọi")
    assert req.status == "REJECTED"
    assert any("deepfake" in a["message"] for a in env.svc.alerts)


def test_tc20_bec_fake_vendor_email(env, ids):
    """Đầu vào giả mạo | Email giả NCC yêu cầu đổi STK, kèm số điện thoại 'liên hệ' | STK không đổi; gọi số trong email bị từ chối; NCC phủ nhận → yêu cầu REJECTED, không thể duyệt"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    c = env.svc.request_account_change(kt, ids["MP"], "ACB", "88886666999", "EMAIL", "LH 0912 345 678")
    assert env.svc.beneficiaries[ids["MP"]].account_no == "0071000123456"
    blocked("SO_GOI_LAI_KHONG_HOP_LE", lambda: env.svc.record_change_callback(ktt, c.id, "0912 345 678", True))
    env.svc.record_change_callback(ktt, c.id, "028 3812 3456", False)
    assert c.status == "REJECTED"
    blocked("CHUA_XAC_MINH", lambda: env.approve_change(ktt, c.id))
    assert env.svc.beneficiaries[ids["MP"]].account_no == "0071000123456"


def test_tc21_cooling_period(env, ids):
    """Đầu vào giả mạo | Tạo lệnh trong 48 giờ ngay sau khi STK NCC được đổi | Lệnh bị CHẶN (thời gian chờ an toàn)"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    c = env.svc.request_account_change(kt, ids["SV"], "Vietinbank", "108866554433", "EMAIL")
    env.svc.record_change_callback(ktt, c.id, "02839991122", True)
    env.approve_change(ktt, c.id)
    env.clock.advance(47 * HOUR)
    kt = env.login("ketoan")
    assert env.svc.create_payment(kt, ids["SV"], 14_000_000, "Cước").status == "BLOCKED"


def test_tc22_account_changed_after_approval(env, ids):
    """Đầu vào giả mạo | Lệnh đã duyệt nhưng STK NCC bị đổi trước khi thực thi | Từ chối TAI_KHOAN_THAY_DOI, lệnh BLOCKED"""
    kt, ktt, gd = env.login("ketoan"), env.login("ketoantruong"), env.login("giamdoc")
    req = env.svc.create_payment(kt, ids["SV"], 14_000_000, "Cước")
    env.approve(ktt, req.id)
    c = env.svc.request_account_change(kt, ids["SV"], "Vietinbank", "108866554433", "EMAIL")
    env.svc.record_change_callback(gd, c.id, "02839991122", True)
    env.approve_change(gd, c.id)
    blocked("TAI_KHOAN_THAY_DOI", lambda: env.svc.execute_payment(kt, req.id))
    assert req.status == "BLOCKED"


# ===================== Sửa đổi dữ liệu / phát lại =====================
def test_tc23_swapped_display(env, ids):
    """Sửa đổi dữ liệu | Mã độc tráo số tiền hiển thị trên màn hình ký (48 triệu → 4,8 triệu) | Chữ ký không khớp nội dung lệnh → từ chối, cảnh báo"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 48_000_000, "Hoá đơn")
    blocked("CHU_KY_KHONG_HOP_LE", lambda: env.approve(ktt, req.id, amount=4_800_000))
    assert not req.approvals


def test_tc24_db_tampering(env, ids):
    """Sửa đổi dữ liệu | Nội gián sửa số tiền/STK trực tiếp trong CSDL sau khi lệnh được duyệt | Thực thi bị từ chối DU_LIEU_BI_SUA_DOI (HMAC toàn vẹn + chữ ký không khớp)"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 44_000_000, "Hoá đơn")
    env.approve(ktt, req.id)
    req.amount = 440_000_000
    blocked("DU_LIEU_BI_SUA_DOI", lambda: env.svc.execute_payment(kt, req.id))
    assert req.status == "BLOCKED"


def test_tc25_signature_replay(env, ids):
    """Sửa đổi dữ liệu | Sử dụng sai ngữ cảnh – dùng chữ ký của lệnh A cho lệnh B; dùng lại chữ ký đã dùng | Từ chối (CHU_KY_KHONG_HOP_LE / CHU_KY_DA_SU_DUNG)"""
    kt, ktt, gd = env.login("ketoan"), env.login("ketoantruong"), env.login("giamdoc")
    a = env.svc.create_payment(kt, ids["MP"], 40_000_000, "Hoá đơn")
    b = env.svc.create_payment(kt, ids["MP"], 40_000_000, "Hoá đơn")
    sig_a = env.wallet.sign_payment(env.svc, a.id, "ketoantruong-phone", "APPROVE")
    env.svc.decide_payment(ktt, a.id, "APPROVE", sig_a)
    sig_gd_a = env.wallet.sign_payment(env.svc, a.id, "giamdoc-phone", "APPROVE")  # chữ ký hợp lệ nhưng cho lệnh A
    blocked("CHU_KY_KHONG_HOP_LE", lambda: env.svc.decide_payment(gd, b.id, "APPROVE", sig_gd_a))
    blocked("CHU_KY_DA_SU_DUNG", lambda: env.svc.decide_payment(gd, b.id, "APPROVE", sig_a))


def test_tc26_reject_signature_not_approve(env, ids):
    """Sửa đổi dữ liệu | Sử dụng sai ngữ cảnh – lấy chữ ký TỪ CHỐI của người duyệt rồi gửi lên như PHÊ DUYỆT | Từ chối vì quyết định nằm trong nội dung được ký"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 40_000_000, "Hoá đơn")
    sig = env.wallet.sign_payment(env.svc, req.id, "ketoantruong-phone", "REJECT")
    blocked("CHU_KY_KHONG_HOP_LE", lambda: env.svc.decide_payment(ktt, req.id, "APPROVE", sig))


def test_tc27_audit_log_tamper(env, ids):
    """Sửa đổi dữ liệu | Sửa nội dung, xoá bản ghi giữa, cắt bỏ bản ghi cuối của nhật ký kiểm toán | Cả 3 trường hợp đều bị phát hiện (chuỗi băm + HMAC + mốc neo)"""
    test_tc02_small_payment(env, ids)
    log = env.svc.audit
    anchor = log.anchor()
    assert log.verify(anchor)[0]
    import copy
    original = copy.deepcopy(log.entries)
    log.entries[5]["details"]["x"] = "sửa"
    assert not log.verify(anchor)[0]
    log.entries = copy.deepcopy(original)
    del log.entries[3]
    assert not log.verify(anchor)[0]
    log.entries = copy.deepcopy(original)[:-2]
    ok, problems = log.verify(anchor)
    assert not ok and any("cắt cụt" in p for p in problems)


# ===================== Phân quyền & kiểm tra đầu vào =====================
def test_tc28_self_approval(env, ids):
    """Phân quyền | Kế toán trưởng tự tạo lệnh rồi tự duyệt | Từ chối TACH_BIET_NHIEM_VU"""
    ktt = env.login("ketoantruong")
    req = env.svc.create_payment(ktt, ids["MP"], 20_000_000, "Tạm ứng")
    blocked("TACH_BIET_NHIEM_VU", lambda: env.approve(ktt, req.id))


def test_tc29_maker_cannot_approve(env, ids):
    """Phân quyền | Kế toán viên cố phê duyệt lệnh của người khác; admin cố tạo lệnh | Từ chối KHONG_CO_QUYEN"""
    kt, ktt, adm = env.login("ketoan"), env.login("ketoantruong"), env.login("admin")
    req = env.svc.create_payment(ktt, ids["MP"], 20_000_000, "Tạm ứng")
    blocked("KHONG_CO_QUYEN", lambda: env.approve(kt, req.id))
    blocked("KHONG_CO_QUYEN", lambda: env.svc.create_payment(adm, ids["MP"], 1_000_000, "x"))


def test_tc30_request_expiry(env, ids):
    """Phân quyền | Phê duyệt lệnh đã quá 24 giờ | Từ chối YEU_CAU_HET_HAN, lệnh EXPIRED"""
    kt = env.login("ketoan")
    req = env.svc.create_payment(kt, ids["MP"], 20_000_000, "Hoá đơn")
    env.clock.advance(25 * HOUR)
    ktt = env.login("ketoantruong")
    blocked("YEU_CAU_HET_HAN", lambda: env.approve(ktt, req.id))
    assert req.status == "EXPIRED"


@pytest.mark.parametrize("amount", [0, -5_000_000, 20_000_000_000, "1000000", 1.5, True])
def test_tc31_invalid_amount(env, ids, amount):
    """Phân quyền | Số tiền không hợp lệ (0, âm, vượt hạn mức 10 tỷ, sai kiểu dữ liệu: chuỗi, số thực, True) | Từ chối DU_LIEU_KHONG_HOP_LE"""
    kt = env.login("ketoan")
    blocked("DU_LIEU_KHONG_HOP_LE", lambda: env.svc.create_payment(kt, ids["MP"], amount, "x"))


def test_tc32_double_approval_and_maker_callback(env, ids):
    """Phân quyền | Một người duyệt 2 lần để đủ số lượng; người tạo lệnh tự ghi nhận gọi lại | Từ chối DA_PHE_DUYET / KHONG_CO_QUYEN"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 120_000_000, "Đặt cọc")
    env.approve(ktt, req.id)
    blocked("DA_PHE_DUYET", lambda: env.approve(ktt, req.id))
    blocked("KHONG_CO_QUYEN", lambda: env.svc.record_payment_callback(kt, req.id, "028 3812 3456", True))


# ===================== Bổ sung: hình ảnh giả mạo =====================
def test_tc33_forged_images(env, ids):
    """Đầu vào giả mạo | Ảnh hoá đơn NCC bị sửa STK gửi qua Zalo; ảnh chụp màn hình 'Giám đốc đã duyệt' | Lệnh theo ảnh hoá đơn bị CHẶN (STK khác sổ đăng ký); ảnh chụp màn hình không được tính là phê duyệt – thiếu chữ ký của chính Giám đốc nên không thực thi được"""
    kt, ktt = env.login("ketoan"), env.login("ketoantruong")
    req = env.svc.create_payment(kt, ids["MP"], 45_000_000, "Thanh toán theo ảnh hoá đơn HĐ 0001240", "IMAGE",
                                 account_no_in_message="0071000999888")
    assert req.status == "BLOCKED" and req.account_no == "0071000123456"
    req = env.svc.create_payment(kt, ids["MP"], 45_000_000, "Ảnh chụp tin nhắn: 'Giám đốc đã duyệt, chuyển luôn'",
                                 "IMAGE", "giamdoc")
    assert req.require_callback and req.required_approvals == 2
    env.approve(ktt, req.id)
    assert any("Lê Hoàng Nam" in g for g in env.svc.approval_gaps(req.id))
    blocked("CHUA_DU_PHE_DUYET", lambda: env.svc.execute_payment(kt, req.id))
