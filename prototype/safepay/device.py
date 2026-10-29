"""Mô phỏng ứng dụng trên điện thoại người dùng: giữ khoá riêng, HIỂN THỊ nội dung cần ký rồi mới ký.

Khoá riêng không bao giờ rời khỏi lớp này – máy chủ chỉ nhận chữ ký.
"""
from .crypto import DeviceKey, canonical


class DeviceWallet:
    def __init__(self):
        self._keys: dict[str, DeviceKey] = {}
        self.owner: dict[str, str] = {}
        self.label: dict[str, str] = {}

    def create(self, device_id: str, owner_username: str, label: str) -> str:
        k = DeviceKey()
        self._keys[device_id] = k
        self.owner[device_id] = owner_username
        self.label[device_id] = label
        return k.public_key_b64

    def devices_of(self, username: str) -> list[str]:
        return [d for d, u in self.owner.items() if u == username]

    def sign(self, device_id: str, payload: dict) -> str:
        return self._keys[device_id].sign(canonical(payload))

    # các thao tác cấp cao
    def sign_login(self, svc, username: str, device_id: str) -> tuple[str, str]:
        ch = svc.start_login(username)
        return ch, self.sign(device_id, svc.login_payload(username, ch, device_id))

    def sign_payment(self, svc, request_id: str, device_id: str, decision: str, shown_override: dict | None = None) -> str:
        """shown_override mô phỏng trường hợp nội dung hiển thị/ký bị tráo (mã độc, MITM)."""
        payload = svc.payment_payload(svc.requests[request_id], decision)
        if shown_override:
            payload = {**payload, **shown_override}
        return self.sign(device_id, payload)

    def sign_change(self, svc, change_id: str, device_id: str) -> str:
        return self.sign(device_id, svc.change_payload(svc.changes[change_id]))
