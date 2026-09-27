# Màn hình khởi động Wisio — Freenove ESP32-S3 LCD 2,8 inch

Đây là bản sao mã nguồn XiaoZhi đã sửa riêng cho bo Freenove. Bản gốc trong Downloads vẫn nguyên vẹn.

Mỗi lần bật nguồn, bo sẽ hiện logo Wisio và thỏ đeo khăn quàng thay biểu tượng robot ban đầu, đồng thời che tên mạch cùng các thông báo quét/kết nối Wi‑Fi. Việc quét và kết nối Wi‑Fi vẫn chạy bình thường. Khi thiết bị sẵn sàng, màn hình trở về giao diện hội thoại. Nếu cần cấu hình Wi‑Fi hoặc có lỗi, thông báo tương ứng vẫn hiện. Các cấu hình bo khác không chứa logo này.

Ảnh `main/wisio_loading_bg.png` có kích thước 320 × 240, dùng phong cách pixel xanh, logo Wisio và thỏ toàn thân đeo khăn quàng có chữ W.

Để build, mở **Espressif PowerShell** trên máy rồi chuyển đến thư mục này và chạy `idf.py build`. Cấu hình `sdkconfig` đã chọn `Freenove ESP32-S3 Display 2.8-inch LCD`. Khi build thành công, kiểm tra kích thước firmware và phân vùng. Muốn nạp qua USB, xác định đúng cổng COM trước, rồi chạy `idf.py -p COMx flash` với cổng đó. Nên giữ bản firmware hiện đang chạy hoặc cách khôi phục trước khi nạp. **File `build/xiaozhi.bin` đang có là bản build cũ; đừng nạp file ấy trước khi build lại thành công.**

Bản có logo trong suốt và lời chúc **chưa được build xong hoặc thử trên robot thật**. Môi trường chạy lệnh của Codex hiện chặn một đường ống tiến trình Windows khi ESP-IDF cấu hình; đây không phải lỗi biên dịch đã xác nhận của phần giao diện mới. Ba kiểm tra mã nguồn liên quan và kiểm tra định dạng phần sửa đã đạt.
