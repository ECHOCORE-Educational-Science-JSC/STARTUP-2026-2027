# Nguồn châm ngôn động viên của Wisio

Danh mục đầu tiên trong `motivational_quotes.py` chỉ chứa bốn câu đã đối chiếu
với các nguồn sau. Bản tiếng Việt là dịch ý của dự án, không phải nguyên văn
tiếng Việt của tác giả. Không có tìm mạng, ảnh hoặc yêu cầu AI phụ khi đang nói.

- Benjamin Franklin: [The Way to Wealth, bản số hóa Project Gutenberg](https://www.gutenberg.org/files/43855/43855-h/43855-h.htm).
  Dùng một trích đoạn ngắn trong lời khuyên về sự chăm chỉ, không coi nỗ lực là
  bảo đảm may mắn hay thành công.
- Thomas Edison: [Thomas Edison National Historical Park — Edison and His Era](https://home.nps.gov/edis/learn/kidsyouth/edison-and-his-era.htm).
  Những tỷ lệ trong câu nói là ẩn dụ nhấn mạnh luyện tập, không phải kết quả nghiên cứu.
- Helen Keller: [American Foundation for the Blind — Quotes on Progress](https://afb.org/about-afb/history/helen-keller/helen-keller-quotes/helen-keller-quotes-progress).
  Nguồn xác định lời trong kịch bản biểu diễn Keller/Anne Sullivan. Dùng để
  khích lệ hợp tác và xin giúp đỡ, không gợi sự phụ thuộc riêng vào robot.
- Nelson Mandela: [Nelson Mandela Foundation — Education Initiatives](https://www.nelsonmandela.org/nm100-education).
  Giải thích hình ảnh ẩn dụ theo giá trị của việc học và làm điều có ích, không diễn giải bạo lực.

Trong hội thoại thường, prompt cho phép dùng thỉnh thoảng theo ngữ cảnh, ưu tiên
lời khích lệ cụ thể. Bộ hẹn giờ chỉ cung cấp một cơ hội dùng câu nói mỗi bốn lời
mời chủ động và cách nhau ít nhất 10 phút; lượt gợi ý không có châm ngôn. Câu
được luân phiên theo từng phiên robot. Khi không hợp ngữ cảnh, model được yêu
cầu bỏ qua, không ép phải trích dẫn. Tần suất trong hội thoại thường và độ chính
xác lời nói cuối cùng vẫn phụ thuộc việc model tuân thủ prompt.

Giữ đúng ngôn ngữ bài học, tối đa một câu, một liên hệ dễ hiểu và một bước nhỏ
vừa sức. Không thêm vào lời giới thiệu, nhạc, hỏi lại do nghe nhầm hoặc dùng để
ép một bé mệt/buồn/đang muốn nghỉ. Không bịa lời rồi gán tên người nổi tiếng.

Đóng bridge cũ rồi mở lại `start_bridge.cmd` để áp dụng. Không cần nạp firmware.
Nếu cập nhật sang thư mục khác, cần chép cả `motivational_quotes.py` đi cùng
`bridge.py`, `PromptWisio.md` và hướng dẫn. Không thay file ký ức hoặc key.
