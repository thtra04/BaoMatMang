"""Chạy toàn bộ kịch bản demo trên terminal:  python demo_cli.py"""
import sys

from safepay.scenarios import run_all

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

for sc in run_all():
    print(f"\n=== {sc['id']} – {sc['title']} ===")
    for i, s in enumerate(sc["steps"], 1):
        print(f"  {i}. [{s['result']}] {s['step']}")
        if s["detail"]:
            print(f"       → {s['detail']}")
