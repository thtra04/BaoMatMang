"""Nhật ký kiểm toán chống sửa đổi: chuỗi băm (hash chain) + HMAC + mốc neo bên ngoài (anchor)."""
from .crypto import canonical, const_eq, hmac_hex, sha256_hex

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, key: bytes, clock):
        self._key = key
        self._clock = clock
        self.entries: list[dict] = []

    def append(self, event: str, actor: str | None, details: dict | None = None) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {
            "seq": len(self.entries),
            "ts": int(self._clock()),
            "event": event,
            "actor": actor,
            "details": details or {},
            "prev": prev,
        }
        h = sha256_hex(canonical(body))
        entry = {**body, "hash": h, "mac": hmac_hex(self._key, h.encode())}
        self.entries.append(entry)
        return entry

    def anchor(self) -> tuple[int, str]:
        """Mốc neo (số thứ tự, hash cuối) – được gửi định kỳ ra ngoài hệ thống (email kiểm toán viên, WORM storage)."""
        if not self.entries:
            return (-1, GENESIS)
        return (self.entries[-1]["seq"], self.entries[-1]["hash"])

    def verify(self, anchor: tuple[int, str] | None = None) -> tuple[bool, list[str]]:
        problems = []
        prev = GENESIS
        for i, e in enumerate(self.entries):
            body = {k: e[k] for k in ("seq", "ts", "event", "actor", "details", "prev")}
            if e["seq"] != i:
                problems.append(f"Bản ghi #{i}: số thứ tự {e['seq']} bị nhảy (có bản ghi bị xoá/chèn)")
            if e["prev"] != prev:
                problems.append(f"Bản ghi #{i}: liên kết tới bản ghi trước bị đứt")
            h = sha256_hex(canonical(body))
            if not const_eq(h, e["hash"]):
                problems.append(f"Bản ghi #{i}: nội dung bị sửa (hash không khớp)")
            if not const_eq(hmac_hex(self._key, e["hash"].encode()), e["mac"]):
                problems.append(f"Bản ghi #{i}: HMAC không hợp lệ (bị giả mạo)")
            prev = e["hash"]
        if anchor is not None:
            seq, h = anchor
            if seq >= len(self.entries):
                problems.append(f"Nhật ký bị cắt cụt: mốc neo ở bản ghi #{seq} nhưng chỉ còn {len(self.entries)} bản ghi")
            elif seq >= 0 and not const_eq(self.entries[seq]["hash"], h):
                problems.append(f"Bản ghi #{seq} không khớp với mốc neo bên ngoài")
        return (not problems, problems)
