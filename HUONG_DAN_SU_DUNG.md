# Hướng dẫn sử dụng Wisio — 28/10/2026

## Chuẩn bị

- Robot đúng board Freenove ESP32-S3 Display 2.8 LCD, flash 16 MB/PSRAM 8 MB; nguồn USB ổn định, cáp dữ liệu USB khi nạp.
- Máy Windows có Python 3.11–3.14 và Internet. Nếu chưa có, cài từ [python.org](https://www.python.org/downloads/windows/) và bật tùy chọn thêm Python vào PATH.
- Gemini API key riêng, tạo tại [Google AI Studio](https://aistudio.google.com/apikey). Nhập key trực tiếp trong cửa sổ bridge; không ghi vào mã nguồn hay gửi lên GitHub.
- Robot dùng Wi-Fi 2.4 GHz. Máy tính và robot phải truy cập được nhau trong cùng mạng; mạng khách có chặn thiết bị sẽ không phù hợp.

## 1. Cài bridge một lần

Giải nén toàn bộ gói vào thư mục riêng. Nhấp đúp `SETUP_BRIDGE.cmd`; chờ tới thông báo cài thành công. Nó tạo môi trường `.venv` riêng và kiểm tra Opus/FFmpeg. Không cần tự cài compiler hoặc ESP-IDF.

Nguồn nhạc Audius có thể dùng ngay. Để nguồn YouTube dự phòng hoạt động đầy đủ, cài Node.js 22+ hoặc Deno 2.3+ rồi mở lại bridge. Chạy `bridge/check_install.py` bằng Python trong `.venv` để xem thành phần còn thiếu. Không cần SerpApi/key tìm ảnh vì ảnh bài học đã tắt.

## 2. Nạp firmware đi kèm

1. Cắm robot bằng cáp dữ liệu USB. Đóng ESP-IDF Serial Monitor và ứng dụng đang giữ cổng COM.
2. Chạy `FLASH_FIRMWARE.cmd`, nhập cổng COM thực tế của robot. Có thể xem trong Device Manager → Ports hoặc dùng “ESP-IDF: Select Port to Use”. Không mặc định máy nào cũng là COM5.
3. Đợi đủ năm file được ghi và xác minh; sau thông báo reset thì nạp đã xong. Script giữ NVS/Wi-Fi đã lưu, không tự mở monitor.

Nạp cả app và `generated_assets.bin` đi cùng để model wake khớp firmware. Chỉ mở file `.bin` trong VS Code không phải là nạp firmware. Không cần tự build nếu dùng bộ binary có sẵn.

## 3. Chạy bridge và nối robot

1. Chạy `START_BRIDGE.cmd`. Nhập Gemini key khi hiện ô nhập ẩn; lúc nhập không thấy ký tự là bình thường. Giữ cửa sổ này mở trong suốt quá trình dùng.
2. Cho phép Python qua Windows Firewall trên mạng **Private** khi Windows hỏi.
3. Bật robot. Nếu chưa lưu mạng, robot vào cấu hình Wi-Fi; nếu kết nối thất bại khoảng 12 giây, robot tự vào cấu hình và phát lời hướng dẫn offline (cần âm lượng khác 0).
4. Kết nối điện thoại vào điểm phát Wisio có tên hiển thị trên màn hình robot. Mở địa chỉ cấu hình mà màn hình chỉ dẫn, chọn mạng 2.4 GHz và nhập mật khẩu.
5. Robot tự tìm bridge trong mạng. Nếu chưa tìm được, dùng URL OTA mà bridge vừa in ra, dạng `http://<IP-máy-tính>:8003/wisio/ota/`, tại mục máy chủ của trang cấu hình robot.
6. Khi log hiện robot đã kết nối và Gemini Live đã kết nối, đợi lời giới thiệu kết thúc rồi nói chuyện.

Bridge dùng TCP 8000 (WebSocket), TCP 8003 (OTA/cấu hình) và UDP 8004 (tìm trong LAN). Bản này chạy trên máy Windows; chưa tự cấu hình VPS/tên miền.

## Sử dụng hằng ngày

- Gọi “Hey Wisio” khi robot đang chờ. Khi nhận đúng sẽ có log “Custom wake word detected”, robot đáp lại và mở mic. **Xanh = đang nghe, vàng = đang nói**.
- Bản khôi phục ưu tiên đường âm thanh mono như trước: tắt tăng giọng PCM và khử vọng phần mềm mới. Wake tạm khóa khi robot đang nói hoặc phát nhạc; gọi khi robot đã về chờ. Log “Wake ready”/“Wake listening” chưa chứng minh đã nhận đúng câu gọi.
- Ví dụ: “Dạy mình về động vật bằng tiếng Anh”, “Giải thích vì sao câu này sai”, “Bật Nơi Này Có Anh của Sơn Tùng M-TP”, “Tăng âm lượng”, “Giảm âm lượng”. Robot xác nhận đổi âm lượng bằng lời, không hiện popup âm lượng.
- Đợi robot trả lời xong khi đang tập câu dài. Khi nghe chưa rõ, robot được hướng dẫn hỏi lại. Tính chủ động có khoảng nghỉ và tôn trọng yêu cầu im lặng.
- Nguồn USB cấp điện khi hoạt động. Firmware không hiện pin yếu, màn hình sạc hoặc tự dừng vì trạng thái sạc; điều này không thay đổi IC sạc vật lý trên board.

## Cập nhật mà giữ ký ức

Tắt bridge cũ bằng Ctrl+C trước khi thay mã. Khi nâng từ bản cũ, dùng cặp firmware/bridge cùng bản này; nạp lại đủ binary rồi mở lại bridge.

Ký ức và hồ sơ học tập nằm ở `bridge/wisio_memory.json` trên **máy tính**, không tự chuyển sang thẻ SD 16 GB. Sao lưu file này riêng trước khi thay thư mục; không lấy file ký ức của máy người khác. Key/email bí mật là cấu hình riêng trên máy và không có trong gói GitHub. Ảnh cache cũ không được dùng trong bài học.

Bản hiện tại chưa tách đầy đủ hồ sơ theo từng robot/người học trong một bridge. Nếu triển khai nhiều bé/robot, cần thiết kế tách hồ sơ trước khi dùng chung dữ liệu ký ức; không coi đây là bản máy chủ nhiều lớp học đã hoàn thiện.

## Xử lý lỗi nhanh

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Không mở được COM / Access is denied | Đóng Serial Monitor/ứng dụng khác; chọn đúng COM sau khi rút/cắm lại. Build thành công không đồng nghĩa cổng đã sẵn sàng |
| Chỉ có dây nguồn, không thấy COM | Thử cáp có dữ liệu và cổng USB khác |
| Robot chưa tới bridge | Kiểm tra cùng LAN, Firewall, mạng khách, URL OTA theo IP hiện tại; không dùng IP cũ của người khác |
| Bridge đóng ngay | Chạy lại `SETUP_BRIDGE.cmd`, kiểm tra Python 3.11–3.14; đọc thông báo cuối cửa sổ |
| Key/quota/model lỗi | Kiểm tra tài khoản và quota của key trong AI Studio; xem mã lỗi cụ thể, không gửi key vào ảnh chụp/log |
| Gọi wake không phản ứng | Kiểm tra đã nạp cả assets, log model `mn5q8_en`/threshold 0.40, mic không bị che và âm lượng vừa; cần thấy dòng nhận diện thật |
| Giọng nhỏ hoặc rè | Nói tăng âm lượng; nếu rè ở mức cao thì giảm lại, kiểm tra nguồn/loa. Bản khôi phục đã tắt tăng giọng PCM, vẫn cần kiểm tra phần cứng |
| Không phát được một bài | Nói rõ tên và ca sĩ; xem log Audius/YouTube, kiểm tra JS runtime. Một số bài bị gỡ/chặn vùng hoặc không cho stream |
| Không có ảnh bài học | Đây là hành vi của bản voice-only; chỉ giữ bìa nhạc |

Khi báo lỗi cho người phát triển, gửi đoạn log từ trước đến sau lỗi, phiên bản 28/10/2026, cổng COM và trạng thái đèn. Che key, email và thông tin riêng của bé.
