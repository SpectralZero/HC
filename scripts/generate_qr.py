"""
CareBox QR Code Generator

Generates QR codes for bags with embedded URLs.
Outputs PNG files and a CSV manifest.

Usage:
    python scripts/generate_qr.py --count 10 --output qr_codes/
"""

import os
import csv
import argparse
import secrets
from datetime import datetime

try:
    import qrcode
    from PIL import Image
except ImportError:
    print("Please install: pip install qrcode pillow")
    exit(1)


def generate_bag_id(prefix: str = "CBX", index: int = 1) -> str:
    """Generate bag ID like CBX-0001."""
    return f"{prefix}-{index:04d}"


def generate_serial() -> str:
    """Generate 8-digit serial number."""
    return f"{secrets.randbelow(100000000):08d}"


def create_qr_code(url: str, size: int = 300) -> Image.Image:
    """Create QR code image for URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    return img.resize((size, size))


def main():
    parser = argparse.ArgumentParser(description="Generate CareBox QR codes")
    parser.add_argument("--count", type=int, default=10, help="Number of QR codes")
    parser.add_argument("--output", type=str, default="qr_codes", help="Output directory")
    parser.add_argument("--base-url", type=str, default="https://carebox.example.com", help="Base URL")
    parser.add_argument("--start", type=int, default=1, help="Starting index")
    parser.add_argument("--prefix", type=str, default="CBX", help="Bag ID prefix")
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Generate bags
    bags = []
    for i in range(args.start, args.start + args.count):
        bag_id = generate_bag_id(args.prefix, i)
        serial = generate_serial()
        serial_last4 = serial[-4:]
        url = f"{args.base_url}/g/{bag_id}"
        
        bags.append({
            "bag_id": bag_id,
            "serial": serial,
            "serial_last4": serial_last4,
            "url": url,
        })
        
        # Generate QR code
        qr_img = create_qr_code(url)
        qr_path = os.path.join(args.output, f"{bag_id}.png")
        qr_img.save(qr_path)
        print(f"Generated: {bag_id} -> {qr_path}")
    
    # Write CSV manifest
    csv_path = os.path.join(args.output, "manifest.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["bag_id", "serial", "serial_last4", "url"])
        writer.writeheader()
        writer.writerows(bags)
    
    print(f"\n✅ Generated {len(bags)} QR codes")
    print(f"📁 Output: {args.output}/")
    print(f"📋 Manifest: {csv_path}")
    print("\n⚠️  Import manifest.csv into Google Sheets BAGS tab")


if __name__ == "__main__":
    main()
