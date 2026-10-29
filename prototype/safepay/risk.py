"""Bộ chấm điểm rủi ro theo luật (rule-based) cho lệnh chuyển tiền.

Nguyên tắc: nội dung đến từ kênh bên ngoài (email, chat, ảnh chụp, cuộc gọi thoại/video) chỉ là
"lời khẳng định chưa được xác minh" – nó làm TĂNG rủi ro chứ không bao giờ làm giảm.
"""
import datetime as dt
import unicodedata
from dataclasses import dataclass, field

EXTERNAL_CHANNELS = {"EMAIL", "CHAT", "IMAGE", "VOICE_CALL", "VIDEO_CALL"}
CHANNELS = {"INTERNAL": "Nhập trực tiếp trên hệ thống",
            "EMAIL": "Email", "CHAT": "Tin nhắn (Zalo/Telegram...)",
            "IMAGE": "Hình ảnh (ảnh chụp hoá đơn / màn hình)",
            "VOICE_CALL": "Cuộc gọi thoại", "VIDEO_CALL": "Cuộc gọi video"}

URGENCY_WORDS = ["gap", "khan", "ngay lap tuc", "bi mat", "giu kin", "dung bao ai",
                 "urgent", "asap", "confidential", "trong hom nay"]

LEVEL_MEDIUM = 30
LEVEL_HIGH = 60
DAY = 86400
VN_TZ = dt.timezone(dt.timedelta(hours=7))


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


@dataclass
class RiskResult:
    score: int = 0
    reasons: list = field(default_factory=list)       # (điểm, mô tả)
    block_reasons: list = field(default_factory=list)  # lý do chặn cứng

    @property
    def blocked(self) -> bool:
        return bool(self.block_reasons)

    @property
    def level(self) -> str:
        if self.blocked:
            return "CRITICAL"
        if self.score >= LEVEL_HIGH:
            return "HIGH"
        if self.score >= LEVEL_MEDIUM:
            return "MEDIUM"
        return "LOW"

    def add(self, points: int, reason: str):
        self.score += points
        self.reasons.append((points, reason))

    def to_dict(self):
        return {"score": self.score, "level": self.level,
                "reasons": [f"+{p}: {r}" for p, r in self.reasons],
                "block_reasons": list(self.block_reasons)}


def assess(*, amount: int, beneficiary, source_channel: str, claimed_by_name: str | None,
           urgent: bool, purpose: str, account_no_in_message: str | None, now: float) -> RiskResult:
    r = RiskResult()

    # --- Luật chặn cứng ---
    if account_no_in_message and account_no_in_message.strip() != beneficiary.account_no:
        r.block_reasons.append(
            f"Số tài khoản trong tin nhắn ({account_no_in_message}) KHÁC số tài khoản đã xác minh "
            f"trong sổ đăng ký ({beneficiary.account_no}) – dấu hiệu lừa đảo đổi tài khoản (BEC)")
    if beneficiary.cooling_until and now < beneficiary.cooling_until:
        r.block_reasons.append(
            "Tài khoản thụ hưởng vừa được thay đổi, đang trong thời gian chờ an toàn 48 giờ")
    if beneficiary.status != "VERIFIED":
        r.block_reasons.append("Người thụ hưởng chưa được xác minh")

    # --- Luật cộng điểm ---
    if source_channel in EXTERNAL_CHANNELS:
        r.add(25, f"Yêu cầu bắt nguồn từ kênh bên ngoài ({CHANNELS[source_channel]}) – nội dung có thể bị giả mạo")
    if claimed_by_name and source_channel in EXTERNAL_CHANNELS:
        r.add(20, f"Yêu cầu tự xưng là của '{claimed_by_name}' nhưng chưa được chính người đó xác nhận trên hệ thống")
    text = _strip_accents(purpose or "")
    if urgent or any(w in text for w in URGENCY_WORDS):
        r.add(15, "Có yếu tố gây áp lực: khẩn cấp / bí mật")
    if not beneficiary.payment_history:
        r.add(20, "Lần đầu chuyển tiền cho người thụ hưởng này")
    elif amount > 3 * (sum(beneficiary.payment_history) / len(beneficiary.payment_history)):
        r.add(20, "Số tiền lớn hơn 3 lần mức trung bình các lần trước")
    if beneficiary.last_changed_at and now - beneficiary.last_changed_at < 30 * DAY:
        r.add(30, "Số tài khoản thụ hưởng bị thay đổi trong vòng 30 ngày")
    local = dt.datetime.fromtimestamp(now, VN_TZ)
    if local.weekday() >= 5 or not (8 <= local.hour < 18):
        r.add(10, "Tạo ngoài giờ làm việc")
    return r
