"""Dữ liệu mẫu dùng chung cho demo web, kịch bản tấn công và kiểm thử."""
import datetime as dt

from .core import ADMIN, CHIEF, DIRECTOR, MAKER, SafePayService
from .crypto import totp_now
from .device import DeviceWallet

VN_TZ = dt.timezone(dt.timedelta(hours=7))

USERS = [
    # username, họ tên, vai trò, mật khẩu, SĐT trong danh bạ nội bộ
    ("ketoan", "Nguyễn Thị Lan", MAKER, "KeToan@2026", "0901 000 001"),
    ("ketoantruong", "Trần Văn Minh", CHIEF, "KTT#Minh2026", "0901 000 002"),
    ("giamdoc", "Lê Hoàng Nam", DIRECTOR, "GD!Nam2026", "0901 000 003"),
    ("phogiamdoc", "Phạm Thu Hà", DIRECTOR, "PGD@Ha2026", "0901 000 004"),
    ("admin", "Võ Quốc Bảo", ADMIN, "Admin#Bao2026", "0901 000 005"),
]

BENEFICIARIES = [
    ("Công ty TNHH Bao Bì Minh Phát", "Vietcombank", "0071000123456", "0312345678", "028 3812 3456",
     [42_000_000, 38_500_000, 45_000_000]),
    ("Công ty CP Vận tải Sao Việt", "BIDV", "31410001234567", "0309876543", "028 3999 1122",
     [12_000_000, 15_000_000, 13_500_000]),
    ("Công ty TNHH Phần mềm An Tâm", "Techcombank", "19033334444015", "0315556677", "028 3777 8899", []),
]


class FakeClock:
    """Đồng hồ điều khiển được để kiểm thử (hết hạn, khoá tạm thời, thời gian chờ...)."""

    def __init__(self, start: float):
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float):
        self.t += seconds


def office_hours_start() -> float:
    """Thứ Tư 28/10/2026, 10:00 giờ Việt Nam."""
    return dt.datetime(2026, 10, 28, 10, 0, tzinfo=VN_TZ).timestamp()


class DemoEnv:
    def __init__(self, clock=None):
        self.clock = clock if clock is not None else FakeClock(office_hours_start())
        self.svc = SafePayService(clock=self.clock)
        self.wallet = DeviceWallet()
        self.passwords: dict[str, str] = {}
        self.totp: dict[str, str] = {}
        self.user_ids: dict[str, str] = {}
        for username, name, role, pw, phone in USERS:
            u, secret = self.svc.create_user(username, name, role, pw, phone)
            self.passwords[username] = pw
            self.totp[username] = secret
            self.user_ids[username] = u.id
            dev_id = f"{username}-phone"
            pk = self.wallet.create(dev_id, username, f"Điện thoại của {name}")
            self.svc.bootstrap_device(u.id, dev_id, pk, f"Điện thoại của {name}")
        self.bene: dict[str, str] = {}
        for name, bank, acc, tax, phone, history in BENEFICIARIES:
            b = self.svc.add_beneficiary(name, bank, acc, tax, phone)
            b.payment_history = list(history)
            self.bene[name] = b.id

    def otp(self, username: str) -> str:
        return totp_now(self.totp[username], self.clock())

    def login(self, username: str, device_id: str | None = None, password: str | None = None,
              otp: str | None = None) -> str:
        if isinstance(self.clock, FakeClock):
            self.clock.advance(31)  # sang chu kỳ OTP mới, tránh trùng mã đã dùng
        device_id = device_id or f"{username}-phone"
        ch, sig = self.wallet.sign_login(self.svc, username, device_id)
        return self.svc.login(username, password or self.passwords[username], otp or self.otp(username), device_id, sig)

    def approve(self, token: str, request_id: str, decision: str = "APPROVE", **override):
        dev = self.svc.session_info(token)["device_id"]
        sig = self.wallet.sign_payment(self.svc, request_id, dev, decision, override or None)
        return self.svc.decide_payment(token, request_id, decision, sig)

    def approve_change(self, token: str, change_id: str):
        dev = self.svc.session_info(token)["device_id"]
        return self.svc.approve_account_change(token, change_id, self.wallet.sign_change(self.svc, change_id, dev))
