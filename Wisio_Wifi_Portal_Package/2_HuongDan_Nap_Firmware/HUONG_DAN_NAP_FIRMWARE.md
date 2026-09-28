# HƯỚNG DẪN NẠP FIRMWARE ECHOCORE CHO BÉ WISIO (ESP32-S3)

Tài liệu này hướng dẫn chi tiết cách biên dịch và nạp firmware **EchoCore** (dành cho bo mạch **Freenove ESP32-S3 Display 2.8" LCD**) có tích hợp giao diện cấu hình Wi-Fi Captive Portal mới nhất.

---

## 1. Yêu Cầu Môi Trường

1. **Phần cứng:** Bo mạch **Freenove ESP32-S3 with 2.8" LCD Screen** (kèm cáp Type-C kết nối máy tính).
2. **Phần mềm:**
   - **ESP-IDF:** v5.5.3 (hoặc v6.0.2).
   - **VS Code:** Đã cài extension chính thức **ESP-IDF** của Espressif.
   - Driver cổng COM: CH340 hoặc CP210x (nếu máy chưa nhận diện cổng COM).

---

## 2. Vị Trí File Giao Diện Wi-Fi Portal Trong Mã Nguồn

File giao diện đã được thiết kế hoàn thiện (giao diện dễ thương, font bo tròn Quicksand/Comfortaa, hiệu ứng vũ trụ lung linh, không có icon thừa, sửa lỗi thanh sóng):

```text
echocore-firmware/main/overrides/esp-wifi-connect/assets/wifi_configuration.html
```

Khi build firmware, hệ thống CMake tự động nhúng (`EMBED_TXTFILES`) file HTML này trực tiếp vào phân vùng flash của vi điều khiển ESP32-S3.

---

## 3. Cách Nạp Bằng VS Code (Khuyên dùng - Đơn giản nhất)

1. **Mở thư mục mã nguồn:**
   - Khởi động VS Code.
   - Chọn `File` -> `Open Folder...` -> Chọn thư mục `echocore-firmware`.

2. **Cấu hình bo mạch trên thanh trạng thái (Status Bar ở đáy VS Code):**
   - Click vào biểu tượng **Target**: Chọn `ESP32-S3`.
   - Click vào biểu tượng **Port**: Chọn đúng cổng COM của bo mạch (ví dụ `COM3`, `COM4`,...).
   - Click vào biểu tượng **Flash Method**: Chọn `UART`.

3. **Biên dịch và nạp (Build & Flash):**
   - Nhấn vào biểu tượng **Build, Flash and Monitor** (hình tia sét ⚡ hoặc chiếc cờ lê 🔧) trên thanh trạng thái.
   - Hoặc dùng phím tắt: Nhấn `Ctrl + E`, nhả tay rồi nhấn `D` (để Build), sau đó `Ctrl + E` rồi nhấn `F` (để Flash).
   - Chờ quá trình nạp đạt `100% (Hash of data verified.)`. Bo mạch sẽ tự khởi động lại.

---

## 4. Cách Nạp Bằng Dòng Lệnh (Terminal / PowerShell)

1. Mở công cụ **ESP-IDF 5.5 PowerShell** (hoặc chạy lệnh export: `. C:\Espressif\frameworks\esp-idf-v5.5.3\export.ps1`).
2. Di chuyển vào thư mục firmware:
   ```powershell
   cd c:\Users\daole\Documents\Codex\2026-09-18\gi-t-i-mu-n-x-2\echocore-firmware
   ```
3. Chạy build theo cấu hình chuẩn của board Freenove:
   ```powershell
   python scripts/build.py freenove-esp32s3-display-2.8-lcd
   ```
4. Nạp vào bo mạch (thay `COMx` bằng cổng COM thực tế của bạn):
   ```powershell
   idf.py -p COMx flash monitor
   ```

## 5. Khôi phục khi reset liên tục hoặc không mở được cổng COM

- Nếu terminal có dòng `Brownout detector was triggered`, dùng cáp USB Type-C ngắn có truyền dữ liệu và cắm trực tiếp vào máy tính. Đây là dấu hiệu điện áp nguồn bị tụt.
- Đóng toàn bộ **ESP-IDF Monitor** trước khi nạp; mỗi Monitor đang chạy đều có thể giữ cổng COM.
- Ở thư mục gốc của dự án, chạy `FLASH_WISIO_COM5.cmd`. Lệnh này nạp ở 115200 và không mở Monitor mới.
- Nếu vẫn không kết nối được, giữ **BOOT**, bấm **RESET** một lần, thả **BOOT**, rồi chạy lại file trên.

---

## 6. Cách Sử Dụng Giao Diện Cấu Hình Wi-Fi Trên Robot

1. Khi robot khởi động mà chưa có mạng Wi-Fi đã lưu, robot sẽ tự động phát mạng Wi-Fi cấu hình (AP mode) tên dạng: `Wisio-Setup` hoặc `EchoCore-WiFi`.
2. Dùng điện thoại hoặc máy tính kết nối vào mạng Wi-Fi này.
3. Trang cấu hình sẽ tự động bật lên (Captive Portal). Nếu không tự bật, mở trình duyệt web và gõ:
   ```text
   http://192.168.4.1
   ```
4. Trên giao diện cực cute:
   - **Mục 1:** Chọn mạng Wi-Fi gia đình bạn muốn kết nối (nhấn Quét lại mạng nếu cần).
   - **Mục 2:** Nhập mật khẩu Wi-Fi (có nút con mắt bật/tắt xem mật khẩu).
   - **Mục 3:** Nhập Email phụ huynh để nhận báo cáo học tập và an toàn của bé.
5. Bấm nút **Kết Nối Wisio!** -> Robot sẽ lưu thông tin, kết nối mạng và bắt đầu hoạt động.
