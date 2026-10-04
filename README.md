# DAMI Threads Assistant — bản dùng API thật

Web quản trị dành cho DAMI Studio, dùng Threads Graph API chính thức để:

- Đăng nhập bằng Meta OAuth hoặc kết nối access token dài hạn.
- Tìm bài công khai theo từ khóa/chủ đề, sắp xếp `RECENT` hoặc `TOP`.
- Chấm điểm tín hiệu nhu cầu, chọn tối đa 10 bài/lượt.
- Tạo bản nháp từ mẫu, sửa riêng từng bình luận và bắt buộc duyệt trước khi gửi.
- Phản hồi bài thật qua `reply_to_id`, lưu ID phản hồi và lịch sử lỗi/thành công.
- Dừng lượt gửi khi người dùng yêu cầu hoặc Meta báo rate limit.
- Mã hóa access token trong SQLite; bảo vệ web bằng mật khẩu quản trị, session và CSRF.

Không có seed, mock hay dữ liệu Threads giả trong mã nguồn.

## Chạy nhanh trên Windows 11

Yêu cầu: Python 3.11 hoặc 3.12.

1. Giải nén dự án.
2. Chạy `setup-windows.bat` một lần.
3. Lưu mật khẩu quản trị được in ra.
4. Mở `.env`, điền `APP_BASE_URL`, `META_APP_ID`, `META_APP_SECRET`.
5. Chạy `run-windows.bat`.
6. Mở `http://127.0.0.1:8765` nếu trình duyệt chưa tự mở.

Đọc [META-SETUP-VI.md](META-SETUP-VI.md) trước khi kết nối tài khoản thật.

## Chạy bằng lệnh

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts/generate_secrets.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Trên macOS/Linux, dòng kích hoạt môi trường là `source .venv/bin/activate`.

## Triển khai HTTPS

Có sẵn:

- `Dockerfile` và `docker-compose.yml`.
- `render.yaml` kèm persistent disk cho SQLite.

Sau khi có URL HTTPS:

1. Đặt URL đó vào `APP_BASE_URL`.
2. Khai báo `APP_BASE_URL/auth/threads/callback` trong Meta App.
3. Redeploy web.

## Quy trình sử dụng

1. Kết nối tài khoản Threads trong **Cài đặt**.
2. Tìm bài theo từ khóa.
3. Chọn tối đa 10 bài và tạo hàng chờ.
4. Đọc bài gốc, sửa phản hồi rồi bấm **Duyệt bình luận**.
5. Bấm **Gửi các mục đã duyệt**.
6. Theo dõi trạng thái và xem lại trong **Lịch sử**.

## Giới hạn an toàn mặc định

- 10 phản hồi mỗi lượt.
- 20 phản hồi mỗi ngày.
- Nghỉ 15 giây giữa hai lần gửi.
- Không tự gửi ngay sau khi tìm kiếm.
- Dừng khi Meta trả lỗi giới hạn tốc độ.

Có thể chỉnh các giới hạn trong `.env`, nhưng `MAX_BATCH_SIZE` luôn tối đa 10.

## Kiểm thử

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

Các test dùng HTTP mock cục bộ để kiểm tra cấu trúc request; không đăng nội dung lên Threads.

