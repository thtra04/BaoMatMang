"""SafePay Guard – lõi nghiệp vụ và chính sách bảo mật.

Mô hình tin cậy (trust model):
  * TIN: chữ ký Ed25519 từ thiết bị đã đăng ký và đang ACTIVE; dữ liệu sổ đăng ký nhà cung cấp
    và danh bạ nhân sự đã được xác minh khi khởi tạo; kết quả gọi lại (call-back) tới số điện thoại
    lấy từ sổ đăng ký.
  * KHÔNG TIN: nội dung email/chat/cuộc gọi thoại/video, số tài khoản hay số điện thoại nằm trong
    tin nhắn, dữ liệu trình duyệt gửi lên, và cả dữ liệu đang nằm trong CSDL (được kiểm tra lại
    bằng HMAC và chữ ký trước khi thực thi).
"""
import os
import time
from dataclasses import dataclass, field

from . import risk as risk_engine
from .audit import AuditLog
from .crypto import (canonical, const_eq, hash_password, hmac_hex, match_totp,
                     new_totp_secret, random_hex, random_token, sha256_hex,
                     verify_password, verify_signature)

MAKER, CHIEF, DIRECTOR, ADMIN = "MAKER", "CHIEF_ACCOUNTANT", "DIRECTOR", "ADMIN"
ROLE_NAMES = {MAKER: "Kế toán viên", CHIEF: "Kế toán trưởng", DIRECTOR: "Giám đốc / Phó GĐ", ADMIN: "Quản trị hệ thống"}
APPROVER_ROLES = {CHIEF, DIRECTOR}

SINGLE_APPROVAL_LIMIT = 50_000_000      # < 50 triệu: 1 người duyệt
DIRECTOR_LIMIT = 500_000_000            # >= 500 triệu: bắt buộc có Giám đốc
MAX_AMOUNT = 10_000_000_000
REQUEST_TTL = 24 * 3600
COOLING_PERIOD = 48 * 3600
MAX_FAILED_LOGINS = 5
LOCKOUT = 15 * 60
SESSION_IDLE = 15 * 60
SESSION_MAX = 8 * 3600
CHALLENGE_TTL = 120


class PolicyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass
class User:
    id: str
    username: str
    full_name: str
    role: str
    password_hash: str
    totp_secret: str
    phone: str
    failed_logins: int = 0
    locked_until: float = 0
    last_totp_counter: int = -1


@dataclass
class Device:
    id: str
    user_id: str
    public_key: str
    label: str
    status: str  # PENDING | ACTIVE | REVOKED
    created_at: float


@dataclass
class Beneficiary:
    id: str
    name: str
    bank: str
    account_no: str
    tax_code: str
    contact_phone: str
    status: str = "VERIFIED"
    last_changed_at: float | None = None
    cooling_until: float | None = None
    payment_history: list = field(default_factory=list)


@dataclass
class AccountChange:
    id: str
    beneficiary_id: str
    new_bank: str
    new_account_no: str
    source_channel: str
    note: str
    submitted_by: str
    created_at: float
    nonce: str
    status: str = "PENDING_CALLBACK"  # -> CALLBACK_OK -> APPLIED | REJECTED
    callback: dict | None = None


@dataclass
class Approval:
    user_id: str
    device_id: str
    decision: str
    signature: str
    payload_hash: str
    ts: float


@dataclass
class PaymentRequest:
    id: str
    maker_id: str
    beneficiary_id: str
    beneficiary_name: str
    bank: str
    account_no: str
    amount: int
    currency: str
    purpose: str
    source_channel: str
    claimed_by: str | None
    urgent: bool
    created_at: float
    expires_at: float
    nonce: str
    status: str
    risk: dict
    required_approvals: int
    require_director: bool
    require_callback: bool
    integrity_mac: str = ""
    approvals: list = field(default_factory=list)
    callback: dict | None = None
    executed_at: float | None = None
    bank_ref: str | None = None


def _digits(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


class SafePayService:
    def __init__(self, clock=None, server_key: bytes | None = None, audit_key: bytes | None = None):
        self.clock = clock or time.time
        self._server_key = server_key or os.urandom(32)
        self.audit = AuditLog(audit_key or os.urandom(32), self.clock)
        self.users: dict[str, User] = {}
        self.devices: dict[str, Device] = {}
        self.beneficiaries: dict[str, Beneficiary] = {}
        self.changes: dict[str, AccountChange] = {}
        self.requests: dict[str, PaymentRequest] = {}
        self.sessions: dict[str, dict] = {}
        self.alerts: list[dict] = []
        self.notifications: list[dict] = []
        self._challenges: dict[str, tuple[str, float]] = {}
        self._used_signatures: set[str] = set()

    # ================= tiện ích nội bộ =================
    def now(self) -> float:
        return self.clock()

    def _user_by_name(self, username: str) -> User | None:
        return next((u for u in self.users.values() if u.username == username), None)

    def _alert(self, level: str, message: str, user_id: str | None = None, **details):
        a = {"ts": int(self.now()), "level": level, "message": message, "user_id": user_id}
        self.alerts.append(a)
        self.audit.append("ALERT", user_id, {"level": level, "message": message, **details})
        if user_id:
            self.notify(user_id, message)

    def notify(self, user_id: str, message: str):
        self.notifications.append({"ts": int(self.now()), "user_id": user_id, "message": message})

    def _fail(self, code: str, message: str, actor: str | None = None, **details):
        self.audit.append("DENIED", actor, {"code": code, "message": message, **details})
        raise PolicyError(code, message)

    def _auth(self, token: str) -> tuple[User, dict]:
        s = self.sessions.get(token)
        now = self.now()
        if not s:
            raise PolicyError("PHIEN_KHONG_HOP_LE", "Phiên đăng nhập không tồn tại hoặc đã bị thu hồi")
        if now - s["last_seen"] > SESSION_IDLE or now - s["created"] > SESSION_MAX:
            del self.sessions[token]
            raise PolicyError("PHIEN_HET_HAN", "Phiên đăng nhập đã hết hạn")
        dev = self.devices.get(s["device_id"])
        if not dev or dev.status != "ACTIVE":
            del self.sessions[token]
            raise PolicyError("THIET_BI_BI_THU_HOI", "Thiết bị của phiên này đã bị thu hồi")
        s["last_seen"] = now
        return self.users[s["user_id"]], s

    def _require_role(self, user: User, roles):
        if user.role not in roles:
            self._fail("KHONG_CO_QUYEN", f"Vai trò {ROLE_NAMES[user.role]} không được phép thực hiện thao tác này", user.id)

    # ================= quản lý người dùng & thiết bị =================
    def create_user(self, username, full_name, role, password, phone) -> tuple[User, str]:
        """Khởi tạo tài khoản (thực hiện trực tiếp bởi bộ phận nhân sự/IT khi nhân viên vào làm)."""
        uid = f"U{len(self.users) + 1:02d}"
        secret = new_totp_secret()
        u = User(uid, username, full_name, role, hash_password(password), secret, phone)
        self.users[uid] = u
        self.audit.append("USER_CREATED", None, {"user": username, "role": role})
        return u, secret

    def bootstrap_device(self, user_id: str, device_id: str, public_key: str, label: str) -> Device:
        """Đăng ký thiết bị đầu tiên – làm trực tiếp tại văn phòng, có đối chiếu giấy tờ."""
        d = Device(device_id, user_id, public_key, label, "ACTIVE", self.now())
        self.devices[device_id] = d
        self.audit.append("DEVICE_BOOTSTRAPPED", user_id, {"device": device_id, "label": label})
        return d

    def request_device_enrollment(self, username, password, otp, device_id, public_key, label) -> Device:
        """Thêm thiết bị mới từ xa: chỉ ở trạng thái PENDING cho tới khi quản trị viên duyệt sau khi gặp trực tiếp/gọi video có đối chiếu."""
        u = self._user_by_name(username)
        if not u or not verify_password(u.password_hash, password) or match_totp(u.totp_secret, otp, self.now()) is None:
            self._fail("DANG_NHAP_THAT_BAI", "Thông tin xác thực không đúng", None, username=username)
        if device_id in self.devices:
            self._fail("THIET_BI_DA_TON_TAI", "Mã thiết bị đã tồn tại", u.id)
        d = Device(device_id, u.id, public_key, label, "PENDING", self.now())
        self.devices[device_id] = d
        self.audit.append("DEVICE_ENROLL_REQUESTED", u.id, {"device": device_id, "label": label})
        self._alert("WARN", f"Có yêu cầu thêm thiết bị mới '{label}' cho tài khoản {u.username}. "
                            f"Nếu không phải bạn, hãy báo ngay cho bộ phận IT.", u.id, device=device_id)
        return d

    def approve_device(self, token: str, device_id: str):
        admin, _ = self._auth(token)
        self._require_role(admin, {ADMIN})
        d = self.devices.get(device_id)
        if not d or d.status != "PENDING":
            self._fail("TRANG_THAI_KHONG_HOP_LE", "Thiết bị không ở trạng thái chờ duyệt", admin.id)
        if d.user_id == admin.id:
            self._fail("TACH_BIET_NHIEM_VU", "Quản trị viên không được tự duyệt thiết bị của mình", admin.id)
        d.status = "ACTIVE"
        self.audit.append("DEVICE_APPROVED", admin.id, {"device": device_id, "owner": d.user_id})
        self.notify(d.user_id, f"Thiết bị '{d.label}' đã được kích hoạt")

    def report_compromise(self, token: str, user_id: str) -> dict:
        """Nút khẩn cấp khi nghi tài khoản/thiết bị bị chiếm: thu hồi mọi thiết bị và phiên,
        đồng thời huỷ hiệu lực mọi phê duyệt chưa thực thi của người dùng đó."""
        actor, _ = self._auth(token)
        if actor.id != user_id and actor.role != ADMIN:
            self._fail("KHONG_CO_QUYEN", "Chỉ chính chủ hoặc quản trị viên được kích hoạt khoá khẩn cấp", actor.id)
        revoked = [d.id for d in self.devices.values() if d.user_id == user_id and d.status != "REVOKED"]
        for did in revoked:
            self.devices[did].status = "REVOKED"
        killed = [t for t, s in self.sessions.items() if s["user_id"] == user_id]
        for t in killed:
            del self.sessions[t]
        reopened = []
        for req in self.requests.values():
            if req.status in ("PENDING_APPROVAL", "APPROVED"):
                before = len(req.approvals)
                req.approvals = [a for a in req.approvals if a.user_id != user_id]
                if len(req.approvals) != before:
                    req.status = "PENDING_APPROVAL"
                    reopened.append(req.id)
        self._alert("CRITICAL", f"Tài khoản {self.users[user_id].username} bị khoá khẩn cấp: thu hồi {len(revoked)} thiết bị, "
                                f"{len(killed)} phiên; huỷ phê duyệt của {len(reopened)} lệnh", actor.id,
                    target=user_id, requests=reopened)
        return {"devices": revoked, "sessions": len(killed), "requests_reopened": reopened}

    # ================= đăng nhập =================
    def start_login(self, username: str) -> str:
        """Trả về challenge ngẫu nhiên kể cả khi username không tồn tại (chống dò tài khoản)."""
        ch = random_hex(16)
        self._challenges[username] = (ch, self.now() + CHALLENGE_TTL)
        return ch

    @staticmethod
    def login_payload(username: str, challenge: str, device_id: str) -> dict:
        return {"type": "LOGIN", "username": username, "challenge": challenge, "device_id": device_id}

    def login(self, username, password, otp, device_id, signature) -> str:
        now = self.now()
        ch = self._challenges.pop(username, None)
        if not ch or now > ch[1]:
            self._fail("CHALLENGE_KHONG_HOP_LE", "Phiên đăng nhập hết hạn, hãy thử lại", None, username=username)
        u = self._user_by_name(username)
        if not u:
            self._fail("DANG_NHAP_THAT_BAI", "Sai thông tin đăng nhập", None, username=username)
        if now < u.locked_until:
            self._fail("TAI_KHOAN_TAM_KHOA", "Tài khoản đang bị tạm khoá do đăng nhập sai nhiều lần", u.id)

        def bad(code, msg):
            u.failed_logins += 1
            if u.failed_logins >= MAX_FAILED_LOGINS:
                u.locked_until = now + LOCKOUT
                u.failed_logins = 0
                self._alert("WARN", f"Tài khoản {u.username} bị khoá 15 phút do đăng nhập sai {MAX_FAILED_LOGINS} lần", u.id)
            self._fail(code, msg, u.id, device=device_id)

        if not verify_password(u.password_hash, password):
            bad("DANG_NHAP_THAT_BAI", "Sai thông tin đăng nhập")
        counter = match_totp(u.totp_secret, otp, now)
        if counter is None:
            bad("OTP_KHONG_HOP_LE", "Mã OTP không đúng hoặc đã hết hạn")
        if counter <= u.last_totp_counter:
            bad("OTP_DA_SU_DUNG", "Mã OTP đã được sử dụng (nghi bị phát lại)")
        dev = self.devices.get(device_id)
        if not dev or dev.user_id != u.id or dev.status != "ACTIVE":
            self._alert("WARN", f"Đăng nhập đúng mật khẩu + OTP nhưng từ thiết bị chưa được đăng ký ({device_id}). "
                                f"Có thể mật khẩu và OTP đã bị lộ.", u.id, device=device_id)
            bad("THIET_BI_CHUA_DANG_KY", "Thiết bị chưa được đăng ký hoặc chưa được kích hoạt")
        payload = canonical(self.login_payload(username, ch[0], device_id))
        if not verify_signature(dev.public_key, payload, signature):
            bad("CHU_KY_KHONG_HOP_LE", "Thiết bị không chứng minh được quyền sở hữu khoá")
        u.failed_logins = 0
        u.last_totp_counter = counter
        token = random_token()
        self.sessions[token] = {"user_id": u.id, "device_id": device_id, "created": now, "last_seen": now}
        self.audit.append("LOGIN_OK", u.id, {"device": device_id})
        return token

    def logout(self, token: str):
        s = self.sessions.pop(token, None)
        if s:
            self.audit.append("LOGOUT", s["user_id"], {})

    def session_info(self, token: str) -> dict:
        u, s = self._auth(token)
        return {"user": u, "device_id": s["device_id"]}

    # ================= sổ đăng ký người thụ hưởng =================
    def add_beneficiary(self, name, bank, account_no, tax_code, contact_phone) -> Beneficiary:
        """Khởi tạo nhà cung cấp (đã đối chiếu hợp đồng, giấy phép KD, xác nhận của ngân hàng)."""
        bid = f"B{len(self.beneficiaries) + 1:02d}"
        b = Beneficiary(bid, name, bank, account_no, tax_code, contact_phone)
        self.beneficiaries[bid] = b
        self.audit.append("BENEFICIARY_ADDED", None, {"id": bid, "name": name, "account_no": account_no})
        return b

    def request_account_change(self, token, beneficiary_id, new_bank, new_account_no, source_channel, note="") -> AccountChange:
        user, _ = self._auth(token)
        b = self.beneficiaries.get(beneficiary_id)
        if not b:
            self._fail("KHONG_TIM_THAY", "Không tìm thấy người thụ hưởng", user.id)
        if source_channel not in risk_engine.CHANNELS:
            self._fail("DU_LIEU_KHONG_HOP_LE", "Kênh nguồn không hợp lệ", user.id)
        cid = f"C{len(self.changes) + 1:03d}"
        c = AccountChange(cid, beneficiary_id, new_bank, new_account_no.strip(), source_channel, note,
                          user.id, self.now(), random_hex(16))
        self.changes[cid] = c
        self.audit.append("ACCOUNT_CHANGE_REQUESTED", user.id,
                          {"change": cid, "beneficiary": b.name, "new_account_no": c.new_account_no, "channel": source_channel})
        self._alert("WARN", f"Yêu cầu đổi STK của '{b.name}' sang {c.new_account_no} – phải gọi lại số "
                            f"trong sổ đăng ký trước khi duyệt", user.id, change=cid)
        return c

    def record_change_callback(self, token, change_id, phone_called, confirmed: bool, note=""):
        user, _ = self._auth(token)
        self._require_role(user, APPROVER_ROLES)
        c = self.changes.get(change_id)
        if not c or c.status != "PENDING_CALLBACK":
            self._fail("TRANG_THAI_KHONG_HOP_LE", "Yêu cầu không ở bước chờ gọi lại", user.id)
        if user.id == c.submitted_by:
            self._fail("TACH_BIET_NHIEM_VU", "Người tiếp nhận yêu cầu không được tự xác minh", user.id)
        b = self.beneficiaries[c.beneficiary_id]
        if _digits(phone_called) != _digits(b.contact_phone):
            self._fail("SO_GOI_LAI_KHONG_HOP_LE",
                       "Phải gọi lại số điện thoại trong sổ đăng ký, không dùng số trong email/tin nhắn", user.id,
                       phone_called=phone_called)
        c.callback = {"by": user.id, "phone": phone_called, "confirmed": confirmed, "note": note, "ts": int(self.now())}
        if confirmed:
            c.status = "CALLBACK_OK"
            self.audit.append("ACCOUNT_CHANGE_CALLBACK_OK", user.id, {"change": change_id})
        else:
            c.status = "REJECTED"
            self._alert("CRITICAL", f"Nhà cung cấp '{b.name}' xác nhận KHÔNG yêu cầu đổi tài khoản – nghi lừa đảo BEC",
                        user.id, change=change_id)

    @staticmethod
    def change_payload(c: AccountChange) -> dict:
        return {"type": "ACCOUNT_CHANGE", "change_id": c.id, "beneficiary_id": c.beneficiary_id,
                "new_bank": c.new_bank, "new_account_no": c.new_account_no, "nonce": c.nonce, "decision": "APPROVE"}

    def approve_account_change(self, token, change_id, signature):
        user, s = self._auth(token)
        self._require_role(user, APPROVER_ROLES)
        c = self.changes.get(change_id)
        if not c or c.status != "CALLBACK_OK":
            self._fail("CHUA_XAC_MINH", "Chưa gọi lại xác minh với nhà cung cấp", user.id)
        if user.id == c.submitted_by:
            self._fail("TACH_BIET_NHIEM_VU", "Người tiếp nhận yêu cầu không được tự duyệt", user.id)
        dev = self.devices[s["device_id"]]
        if not verify_signature(dev.public_key, canonical(self.change_payload(c)), signature):
            self._fail("CHU_KY_KHONG_HOP_LE", "Chữ ký phê duyệt không hợp lệ", user.id)
        b = self.beneficiaries[c.beneficiary_id]
        old = b.account_no
        b.bank, b.account_no = c.new_bank, c.new_account_no
        b.last_changed_at = self.now()
        b.cooling_until = self.now() + COOLING_PERIOD
        c.status = "APPLIED"
        self.audit.append("ACCOUNT_CHANGE_APPLIED", user.id,
                          {"change": change_id, "old": old, "new": c.new_account_no, "signature": signature})

    # ================= lệnh chuyển tiền =================
    @staticmethod
    def payment_payload(req: PaymentRequest, decision: str) -> dict:
        """Đúng những gì thiết bị hiển thị cho người duyệt và ký (What You See Is What You Sign)."""
        return {"type": "PAYMENT_DECISION", "request_id": req.id, "beneficiary_name": req.beneficiary_name,
                "bank": req.bank, "account_no": req.account_no, "amount": req.amount, "currency": req.currency,
                "purpose": req.purpose, "nonce": req.nonce, "expires_at": int(req.expires_at), "decision": decision}

    def _integrity_mac(self, req: PaymentRequest) -> str:
        core = {k: getattr(req, k) for k in ("id", "maker_id", "beneficiary_id", "beneficiary_name", "bank",
                                             "account_no", "amount", "currency", "purpose", "source_channel",
                                             "claimed_by", "nonce", "required_approvals", "require_director",
                                             "require_callback")}
        core["expires_at"] = int(req.expires_at)
        return hmac_hex(self._server_key, canonical(core))

    def create_payment(self, token, beneficiary_id, amount, purpose, source_channel="INTERNAL",
                       claimed_by_username=None, urgent=False, account_no_in_message=None) -> PaymentRequest:
        user, _ = self._auth(token)
        self._require_role(user, {MAKER, CHIEF, DIRECTOR})
        b = self.beneficiaries.get(beneficiary_id)
        if not b:
            self._fail("KHONG_TIM_THAY", "Không tìm thấy người thụ hưởng trong sổ đăng ký", user.id)
        if type(amount) is not int or not (0 < amount <= MAX_AMOUNT):  # bool là lớp con của int
            self._fail("DU_LIEU_KHONG_HOP_LE", "Số tiền không hợp lệ", user.id)
        if source_channel not in risk_engine.CHANNELS:
            self._fail("DU_LIEU_KHONG_HOP_LE", "Kênh nguồn không hợp lệ", user.id)
        claimed = None
        if claimed_by_username:
            claimed = self._user_by_name(claimed_by_username)
            if not claimed or claimed.role not in APPROVER_ROLES:
                self._fail("DU_LIEU_KHONG_HOP_LE", "Người yêu cầu được nêu không phải người có thẩm quyền duyệt", user.id)
        now = self.now()
        r = risk_engine.assess(amount=amount, beneficiary=b, source_channel=source_channel,
                               claimed_by_name=claimed.full_name if claimed else None, urgent=urgent,
                               purpose=purpose, account_no_in_message=account_no_in_message, now=now)
        required = 1 if amount < SINGLE_APPROVAL_LIMIT else 2
        require_director = amount >= DIRECTOR_LIMIT
        require_callback = claimed is not None
        if r.level == "MEDIUM":
            required = max(required, 2)
        if r.level == "HIGH":
            required, require_director, require_callback = max(required, 2), True, True
        rid = f"PR-{len(self.requests) + 1:04d}"
        # Thông tin thụ hưởng LUÔN lấy từ sổ đăng ký, không lấy từ tin nhắn
        req = PaymentRequest(rid, user.id, b.id, b.name, b.bank, b.account_no, amount, "VND", purpose,
                             source_channel, claimed.id if claimed else None, urgent, now, now + REQUEST_TTL,
                             random_hex(16), "BLOCKED" if r.blocked else "PENDING_APPROVAL", r.to_dict(),
                             required, require_director, require_callback)
        req.integrity_mac = self._integrity_mac(req)
        self.requests[rid] = req
        self.audit.append("PAYMENT_CREATED", user.id, {"request": rid, "amount": amount, "beneficiary": b.name,
                                                       "channel": source_channel, "risk": r.to_dict()})
        if r.blocked:
            self._alert("CRITICAL", f"Lệnh {rid} bị CHẶN: " + "; ".join(r.block_reasons), user.id, request=rid)
        elif claimed:
            self.notify(claimed.id, f"Có lệnh {rid} ({amount:,} VND) ghi là do bạn yêu cầu qua "
                                    f"{risk_engine.CHANNELS[source_channel]}. Nếu không phải bạn, hãy TỪ CHỐI.")
        return req

    def decide_payment(self, token, request_id, decision, signature) -> PaymentRequest:
        user, s = self._auth(token)
        self._require_role(user, APPROVER_ROLES)
        req = self.requests.get(request_id)
        if not req:
            self._fail("KHONG_TIM_THAY", "Không tìm thấy lệnh", user.id)
        if decision not in ("APPROVE", "REJECT"):
            self._fail("DU_LIEU_KHONG_HOP_LE", "Quyết định không hợp lệ", user.id)
        if req.status != "PENDING_APPROVAL":
            self._fail("TRANG_THAI_KHONG_HOP_LE", f"Lệnh đang ở trạng thái {req.status}", user.id)
        if user.id == req.maker_id:
            self._fail("TACH_BIET_NHIEM_VU", "Người tạo lệnh không được tự phê duyệt", user.id, request=request_id)
        if any(a.user_id == user.id for a in req.approvals):
            self._fail("DA_PHE_DUYET", "Mỗi người chỉ được phê duyệt một lần", user.id)
        if self.now() > req.expires_at:
            req.status = "EXPIRED"
            self._fail("YEU_CAU_HET_HAN", "Lệnh đã hết hạn", user.id, request=request_id)
        if signature in self._used_signatures:
            self._fail("CHU_KY_DA_SU_DUNG", "Chữ ký đã được sử dụng trước đó (tấn công phát lại)", user.id)
        dev = self.devices[s["device_id"]]
        payload = canonical(self.payment_payload(req, decision))
        if not verify_signature(dev.public_key, payload, signature):
            self._alert("CRITICAL", f"Chữ ký phê duyệt lệnh {request_id} không khớp nội dung lệnh – nội dung có thể đã bị "
                                    f"tráo giữa lúc hiển thị và lúc ký", user.id, request=request_id)
            self._fail("CHU_KY_KHONG_HOP_LE", "Chữ ký không khớp với nội dung lệnh", user.id, request=request_id)
        self._used_signatures.add(signature)
        req.approvals.append(Approval(user.id, dev.id, decision, signature, sha256_hex(payload), self.now()))
        self.audit.append("PAYMENT_" + decision, user.id, {"request": request_id, "device": dev.id, "signature": signature})
        if decision == "REJECT":
            req.status = "REJECTED"
        else:
            self._maybe_approve(req)
        return req

    def record_payment_callback(self, token, request_id, phone_called, confirmed: bool, note=""):
        """Gọi lại xác minh ngoài băng (out-of-band) – số gọi phải lấy từ danh bạ nội bộ / sổ đăng ký."""
        user, _ = self._auth(token)
        self._require_role(user, APPROVER_ROLES)
        req = self.requests.get(request_id)
        if not req or req.status != "PENDING_APPROVAL":
            self._fail("TRANG_THAI_KHONG_HOP_LE", "Lệnh không ở trạng thái chờ duyệt", user.id)
        if user.id == req.maker_id:
            self._fail("TACH_BIET_NHIEM_VU", "Người tạo lệnh không được tự xác minh", user.id)
        expected = self.users[req.claimed_by].phone if req.claimed_by else self.beneficiaries[req.beneficiary_id].contact_phone
        if _digits(phone_called) != _digits(expected):
            self._fail("SO_GOI_LAI_KHONG_HOP_LE",
                       "Phải gọi lại số trong danh bạ nội bộ/sổ đăng ký, không dùng số do người yêu cầu cung cấp",
                       user.id, phone_called=phone_called)
        req.callback = {"by": user.id, "phone": phone_called, "confirmed": confirmed, "note": note, "ts": int(self.now())}
        self.audit.append("PAYMENT_CALLBACK", user.id, {"request": request_id, "confirmed": confirmed})
        if not confirmed:
            req.status = "REJECTED"
            self._alert("CRITICAL", f"Lệnh {request_id}: người được gọi lại xác nhận KHÔNG yêu cầu – nghi giả mạo "
                                    f"(deepfake/BEC)", user.id, request=request_id)
        else:
            self._maybe_approve(req)

    def _approval_gaps(self, req: PaymentRequest) -> list[str]:
        ok = [a for a in req.approvals if a.decision == "APPROVE"]
        gaps = []
        if len(ok) < req.required_approvals:
            gaps.append(f"Cần {req.required_approvals} người duyệt, mới có {len(ok)}")
        if req.require_director and not any(self.users[a.user_id].role == DIRECTOR for a in ok):
            gaps.append("Cần chữ ký của Giám đốc / Phó Giám đốc")
        if req.claimed_by and not any(a.user_id == req.claimed_by for a in ok):
            gaps.append(f"Cần chính {self.users[req.claimed_by].full_name} ký xác nhận trên thiết bị đã đăng ký")
        if req.require_callback and not (req.callback and req.callback["confirmed"]):
            gaps.append("Cần gọi lại xác minh qua số điện thoại trong danh bạ/sổ đăng ký")
        return gaps

    def approval_gaps(self, request_id: str) -> list[str]:
        return self._approval_gaps(self.requests[request_id])

    def _maybe_approve(self, req: PaymentRequest):
        if req.status == "PENDING_APPROVAL" and not self._approval_gaps(req):
            req.status = "APPROVED"
            self.audit.append("PAYMENT_APPROVED", None, {"request": req.id})

    def execute_payment(self, token, request_id) -> PaymentRequest:
        """Gửi lệnh sang ngân hàng. Mọi điều kiện được kiểm tra LẠI từ đầu (không tin trạng thái trong CSDL)."""
        user, _ = self._auth(token)
        self._require_role(user, {MAKER, CHIEF})
        req = self.requests.get(request_id)
        if not req:
            self._fail("KHONG_TIM_THAY", "Không tìm thấy lệnh", user.id)
        if req.status != "APPROVED":
            self._fail("CHUA_DU_PHE_DUYET", "Lệnh chưa đủ điều kiện thực thi: " + "; ".join(self._approval_gaps(req) or [req.status]),
                       user.id, request=request_id)
        if not const_eq(self._integrity_mac(req), req.integrity_mac):
            req.status = "BLOCKED"
            self._alert("CRITICAL", f"Lệnh {request_id} bị sửa trực tiếp trong CSDL sau khi tạo (HMAC không khớp)",
                        user.id, request=request_id)
            self._fail("DU_LIEU_BI_SUA_DOI", "Dữ liệu lệnh bị thay đổi trái phép", user.id, request=request_id)
        for a in req.approvals:
            dev = self.devices.get(a.device_id)
            payload = canonical(self.payment_payload(req, a.decision))
            if not dev or dev.status != "ACTIVE" or not verify_signature(dev.public_key, payload, a.signature):
                req.status = "BLOCKED"
                self._alert("CRITICAL", f"Lệnh {request_id}: chữ ký phê duyệt không còn hợp lệ", user.id, request=request_id)
                self._fail("CHU_KY_KHONG_HOP_LE", "Chữ ký phê duyệt không còn khớp với nội dung lệnh", user.id)
        if self._approval_gaps(req):
            self._fail("CHUA_DU_PHE_DUYET", "; ".join(self._approval_gaps(req)), user.id)
        if self.now() > req.expires_at:
            req.status = "EXPIRED"
            self._fail("YEU_CAU_HET_HAN", "Lệnh đã hết hạn", user.id)
        b = self.beneficiaries[req.beneficiary_id]
        if b.account_no != req.account_no or (b.cooling_until and self.now() < b.cooling_until):
            req.status = "BLOCKED"
            self._alert("CRITICAL", f"Lệnh {request_id}: tài khoản thụ hưởng đã thay đổi kể từ lúc duyệt", user.id)
            self._fail("TAI_KHOAN_THAY_DOI", "Tài khoản thụ hưởng đã thay đổi kể từ lúc phê duyệt", user.id)
        req.status = "EXECUTED"
        req.executed_at = self.now()
        req.bank_ref = "FT" + random_hex(5).upper()
        b.payment_history.append(req.amount)
        self.audit.append("PAYMENT_EXECUTED", user.id, {"request": request_id, "amount": req.amount,
                                                        "account_no": req.account_no, "bank_ref": req.bank_ref})
        return req
