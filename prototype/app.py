"""Giao diện web demo SafePay Guard.   Chạy:  python app.py   rồi mở http://127.0.0.1:5000"""
import datetime as dt
import json
import secrets
import time

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from safepay.core import APPROVER_ROLES, CHIEF, DIRECTOR, MAKER, ADMIN, ROLE_NAMES, PolicyError
from safepay.risk import CHANNELS
from safepay.scenarios import run_all
from safepay.seed import USERS, DemoEnv, VN_TZ

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

STATE = {"env": DemoEnv(clock=time.time), "anchor": None}


def env() -> DemoEnv:
    return STATE["env"]


@app.template_filter("vnd")
def vnd(x):
    return f"{x:,}".replace(",", ".") + " đ"


@app.template_filter("j")
def j(x):
    return json.dumps(x, ensure_ascii=False)


@app.template_filter("ts")
def ts(x):
    return dt.datetime.fromtimestamp(x, VN_TZ).strftime("%d/%m %H:%M:%S") if x else ""


@app.context_processor
def globals_():
    return {"ROLE_NAMES": ROLE_NAMES, "CHANNELS": CHANNELS, "me": current(), "svc": env().svc}


def current():
    tok = session.get("token")
    if not tok:
        return None
    try:
        info = env().svc.session_info(tok)
        return {"token": tok, "user": info["user"], "device_id": info["device_id"]}
    except PolicyError:
        session.pop("token", None)
        return None


def guarded(fn):
    """Chạy một thao tác nghiệp vụ, hiển thị lỗi chính sách thành thông báo."""
    try:
        res = fn()
        return True, res
    except PolicyError as e:
        flash(f"Bị từ chối – {e.code}: {e.message}", "error")
        return False, None


# ---------------- đăng nhập ----------------
@app.get("/")
def index():
    me = current()
    if not me:
        return render_template("login.html", users=USERS, devices=env().wallet.owner)
    svc = env().svc
    reqs = sorted(svc.requests.values(), key=lambda r: r.created_at, reverse=True)
    notes = [n for n in svc.notifications if n["user_id"] == me["user"].id][-8:][::-1]
    alerts = svc.alerts[-10:][::-1] if me["user"].role in APPROVER_ROLES | {ADMIN} else []
    return render_template("dashboard.html", reqs=reqs, notes=notes, alerts=alerts,
                           can_create=me["user"].role in (MAKER, CHIEF, DIRECTOR),
                           approvers=[u for u in svc.users.values() if u.role in APPROVER_ROLES])


@app.get("/otp")
def otp_codes():
    """Mô phỏng ứng dụng Authenticator trên điện thoại từng người (chỉ để demo)."""
    e = env()
    return jsonify({u: e.otp(u) for u in e.totp} | {"_remain": 30 - int(time.time()) % 30})


@app.post("/login")
def login():
    e = env()
    f = request.form
    username, device_id = f["username"].strip(), f["device_id"]
    if device_id not in e.wallet.owner:
        flash("Thiết bị không tồn tại trong mô phỏng", "error")
        return redirect(url_for("index"))
    ch, sig = e.wallet.sign_login(e.svc, username, device_id)
    ok, tok = guarded(lambda: e.svc.login(username, f["password"], f["otp"].strip(), device_id, sig))
    if ok:
        session["token"] = tok
        flash(f"Đăng nhập thành công từ thiết bị {device_id}", "ok")
    return redirect(url_for("index"))


@app.post("/enroll")
def enroll():
    e = env()
    f = request.form
    dev_id = f"new-{secrets.token_hex(3)}"
    pk = e.wallet.create(dev_id, f["username"], f["label"] or "Thiết bị mới")
    ok, d = guarded(lambda: e.svc.request_device_enrollment(f["username"], f["password"], f["otp"], dev_id, pk, f["label"]))
    if ok:
        flash(f"Đã gửi yêu cầu thêm thiết bị {dev_id} – trạng thái {d.status}, chờ quản trị viên duyệt", "ok")
    return redirect(url_for("index"))


@app.get("/logout")
def logout():
    if session.get("token"):
        env().svc.logout(session.pop("token"))
    return redirect(url_for("index"))


@app.post("/reset")
def reset():
    STATE["env"] = DemoEnv(clock=time.time)
    STATE["anchor"] = None
    session.clear()
    flash("Đã khởi tạo lại dữ liệu demo", "ok")
    return redirect(url_for("index"))


# ---------------- lệnh chuyển tiền ----------------
@app.post("/payments")
def create_payment():
    me = current()
    if not me:
        return redirect(url_for("index"))
    f = request.form
    try:
        amount = int(f["amount"].replace(".", "").replace(",", ""))
    except ValueError:
        flash("Số tiền không hợp lệ", "error")
        return redirect(url_for("index"))
    ok, req = guarded(lambda: env().svc.create_payment(
        me["token"], f["beneficiary_id"], amount, f["purpose"], f["channel"],
        f.get("claimed_by") or None, bool(f.get("urgent")), f.get("account_in_msg") or None))
    if ok:
        return redirect(url_for("payment", rid=req.id))
    return redirect(url_for("index"))


@app.get("/payments/<rid>")
def payment(rid):
    me = current()
    if not me:
        return redirect(url_for("index"))
    svc = env().svc
    req = svc.requests.get(rid)
    if not req:
        return redirect(url_for("index"))
    return render_template("payment.html", req=req, payload=svc.payment_payload(req, "APPROVE"),
                           gaps=svc.approval_gaps(rid), bene=svc.beneficiaries[req.beneficiary_id])


@app.post("/payments/<rid>/decide")
def decide(rid):
    me = current()
    if not me:
        return redirect(url_for("index"))
    e = env()
    decision = request.form["decision"]
    override = None
    if request.form.get("tamper"):
        # mô phỏng mã độc tráo nội dung: điện thoại hiển thị/ký số tiền nhỏ hơn 10 lần
        override = {"amount": e.svc.requests[rid].amount // 10}
    sig = e.wallet.sign_payment(e.svc, rid, me["device_id"], decision, override)
    ok, _ = guarded(lambda: e.svc.decide_payment(me["token"], rid, decision, sig))
    if ok:
        flash("Đã ghi nhận chữ ký " + ("phê duyệt" if decision == "APPROVE" else "từ chối"), "ok")
    return redirect(url_for("payment", rid=rid))


@app.post("/payments/<rid>/callback")
def callback(rid):
    me = current()
    if not me:
        return redirect(url_for("index"))
    f = request.form
    ok, _ = guarded(lambda: env().svc.record_payment_callback(me["token"], rid, f["phone"], f["confirmed"] == "yes", f.get("note", "")))
    if ok:
        flash("Đã ghi nhận kết quả gọi lại", "ok")
    return redirect(url_for("payment", rid=rid))


@app.post("/payments/<rid>/execute")
def execute(rid):
    me = current()
    if not me:
        return redirect(url_for("index"))
    ok, req = guarded(lambda: env().svc.execute_payment(me["token"], rid))
    if ok:
        flash(f"Đã gửi lệnh sang ngân hàng – mã giao dịch {req.bank_ref}", "ok")
    return redirect(url_for("payment", rid=rid))


@app.post("/payments/<rid>/tamper-db")
def tamper_db(rid):
    """Mô phỏng kẻ nội gián sửa trực tiếp CSDL (bỏ qua mọi API)."""
    req = env().svc.requests[rid]
    req.account_no = request.form.get("account_no") or "970422998811"
    flash(f"[TẤN CÔNG] Đã sửa trực tiếp STK của {rid} trong CSDL thành {req.account_no}", "warn")
    return redirect(url_for("payment", rid=rid))


# ---------------- người thụ hưởng ----------------
@app.get("/beneficiaries")
def beneficiaries():
    if not current():
        return redirect(url_for("index"))
    svc = env().svc
    return render_template("beneficiaries.html", benes=svc.beneficiaries.values(),
                           changes=sorted(svc.changes.values(), key=lambda c: c.created_at, reverse=True))


@app.post("/changes")
def create_change():
    me = current()
    f = request.form
    ok, c = guarded(lambda: env().svc.request_account_change(me["token"], f["beneficiary_id"], f["bank"],
                                                             f["account_no"], f["channel"], f.get("note", "")))
    if ok:
        flash(f"Đã tạo yêu cầu {c.id} – cần gọi lại số trong sổ đăng ký", "ok")
    return redirect(url_for("beneficiaries"))


@app.post("/changes/<cid>/callback")
def change_callback(cid):
    me = current()
    f = request.form
    ok, _ = guarded(lambda: env().svc.record_change_callback(me["token"], cid, f["phone"], f["confirmed"] == "yes", f.get("note", "")))
    if ok:
        flash("Đã ghi nhận kết quả gọi lại", "ok")
    return redirect(url_for("beneficiaries"))


@app.post("/changes/<cid>/approve")
def change_approve(cid):
    me = current()
    e = env()
    ok, _ = guarded(lambda: e.svc.approve_account_change(me["token"], cid, e.wallet.sign_change(e.svc, cid, me["device_id"])))
    if ok:
        flash("Đã đổi số tài khoản – bắt đầu 48 giờ chờ an toàn", "ok")
    return redirect(url_for("beneficiaries"))


# ---------------- thiết bị / khoá khẩn cấp ----------------
@app.get("/security")
def security():
    if not current():
        return redirect(url_for("index"))
    svc = env().svc
    return render_template("security.html", devices=svc.devices.values(), users=svc.users)


@app.post("/devices/<did>/approve")
def device_approve(did):
    me = current()
    ok, _ = guarded(lambda: env().svc.approve_device(me["token"], did))
    if ok:
        flash(f"Đã kích hoạt thiết bị {did}", "ok")
    return redirect(url_for("security"))


@app.post("/compromise/<uid>")
def compromise(uid):
    me = current()
    ok, res = guarded(lambda: env().svc.report_compromise(me["token"], uid))
    if ok:
        flash(f"Khoá khẩn cấp: thu hồi {res['devices']}, huỷ duyệt {res['requests_reopened']}", "warn")
    return redirect(url_for("security") if current() else url_for("index"))


# ---------------- nhật ký kiểm toán ----------------
@app.get("/audit")
def audit():
    if not current():
        return redirect(url_for("index"))
    log = env().svc.audit
    ok, problems = log.verify(STATE["anchor"])
    return render_template("audit.html", entries=log.entries[::-1], ok=ok, problems=problems, anchor=STATE["anchor"])


@app.post("/audit/<action>")
def audit_action(action):
    log = env().svc.audit
    if action == "anchor":
        STATE["anchor"] = log.anchor()
        flash(f"Đã gửi mốc neo #{STATE['anchor'][0]} ra hệ thống lưu trữ bên ngoài", "ok")
    elif action == "tamper" and log.entries:
        target = next((e for e in reversed(log.entries) if e["event"] == "PAYMENT_EXECUTED"), log.entries[-1])
        target["details"]["tampered"] = "đã bị sửa"
        flash(f"[TẤN CÔNG] Đã sửa bản ghi #{target['seq']}", "warn")
    elif action == "truncate" and len(log.entries) > 2:
        del log.entries[-2:]
        flash("[TẤN CÔNG] Đã xoá 2 bản ghi cuối", "warn")
    return redirect(url_for("audit"))


@app.get("/scenarios")
def scenarios():
    return render_template("scenarios.html", results=run_all())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
