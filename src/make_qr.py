import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

qr = qrcode.QRCode(
    version=None,              # None = tự chọn kích thước nhỏ nhất đủ chứa
    error_correction=ERROR_CORRECT_M,  # L(7%) M(15%) Q(25%) H(30%) — H nếu chèn logo
    box_size=16,               # px mỗi ô → ảnh càng nét/to
    border=1,                  # viền trắng (đơn vị = số ô), tối thiểu nên 4 cho máy quét phổ thông
)
qr.add_data("https://github.com/trungiemiu/pdvrp-free-end-alns")
qr.make(fit=True)
img = qr.make_image(fill_color="#141225", back_color="white").convert("RGB")
img.save("outputs/qr.png")