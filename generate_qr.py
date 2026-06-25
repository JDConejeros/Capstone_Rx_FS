#!/usr/bin/env python3
"""Generate QR code for the Capstone Streamlit app."""

from pathlib import Path

import qrcode

APP_URL = "https://capstone-rx-fs.streamlit.app/"
OUTPUT = Path(__file__).parent / "image" / "capstone_qr.png"


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(APP_URL)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A5F", back_color="white")
    img.save(OUTPUT)
    print(f"QR saved: {OUTPUT}")
    print(f"URL: {APP_URL}")


if __name__ == "__main__":
    main()
