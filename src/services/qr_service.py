# src/services/qr_service.py
# QR Code 生成服務

import uuid


def generate_qr_code(prefix: str = "QR") -> str:
    """
    生成唯一的 QR Code 識別碼。

    格式：{prefix}_{12位隨機十六進制字串}
    例如：QR_A1B2C3D4E5F6

    Args:
        prefix: QR Code 前綴，預設為 "QR"

    Returns:
        唯一的 QR Code 字串
    """
    unique_id = uuid.uuid4().hex[:12].upper()
    return f"{prefix}_{unique_id}"


def generate_homeless_qr_code() -> str:
    """生成街友專用 QR Code"""
    return generate_qr_code(prefix="HL")


def generate_store_qr_code() -> str:
    """生成商店專用 QR Code"""
    return generate_qr_code(prefix="ST")
