# Cấu hình Meta Threads API thật

Web này **không có dữ liệu demo**. Muốn tìm và phản hồi bài thật, tài khoản phải có access token hợp lệ với ba quyền:

- `threads_basic`
- `threads_content_publish`
- `threads_keyword_search`

## 1. Tạo Meta App

1. Mở [Meta for Developers](https://developers.facebook.com/apps/).
2. Tạo App mới và chọn use case **Access the Threads API**.
3. Trong phần Threads API, lấy đúng **Threads App ID** và **Threads App Secret**. Hai giá trị này có thể khác App ID/Secret chung hiển thị ở đầu trang.
4. Thêm tài khoản Threads của DAMI Studio vào vai trò **Threads Tester** và chấp nhận lời mời trên tài khoản đó.

## 2. Khai báo OAuth callback

Sau khi triển khai web lên tên miền HTTPS, đặt:

```text
APP_BASE_URL=https://ten-mien-cua-ban.example
```

Callback chính xác của web là:

```text
https://ten-mien-cua-ban.example/auth/threads/callback
```

Sao chép nguyên callback này vào **Valid OAuth Redirect URIs** của Threads API. Không thêm hoặc bỏ dấu `/` ở cuối.

## 3. Điền `.env`

```env
APP_BASE_URL=https://ten-mien-cua-ban.example
META_APP_ID=Threads_App_ID
META_APP_SECRET=Threads_App_Secret
```

Không đưa `.env`, App Secret hoặc access token lên GitHub.

## 4. Kết nối tài khoản

1. Đăng nhập trang quản trị.
2. Mở tab **Cài đặt**.
3. Bấm **Kết nối bằng Meta OAuth**.
4. Chấp nhận đúng ba quyền được yêu cầu.
5. Khi quay lại web, kiểm tra góc trên bên phải đã hiện `@username`.

## 5. Chế độ Development và App Review

- Khi App còn ở Development, chỉ tài khoản có vai trò trong App (Admin/Developer/Threads Tester) dùng được.
- Nếu muốn người ngoài vai trò App đăng nhập, phải chuyển App sang Live và hoàn tất App Review cho các quyền tương ứng.
- `threads_keyword_search` có thể bị giới hạn kết quả cho tới khi quyền được duyệt. Đây là giới hạn từ Meta, không phải dữ liệu giả của web.

## 6. Chạy local trên Windows

Threads OAuth yêu cầu callback HTTPS hợp lệ. Khi chạy ở `http://127.0.0.1:8765`, hãy dùng một trong hai cách:

- Tạo đường hầm HTTPS và đặt URL đó vào `APP_BASE_URL`; hoặc
- Tạo token dài hạn trong công cụ của Meta, rồi dán token vào mục **Dùng token dài hạn** trong tab Cài đặt.

Token được mã hóa trước khi lưu vào SQLite. Không gửi token hoặc App Secret qua tin nhắn.

## 7. Kiểm tra quyền

Nếu tìm kiếm báo lỗi quyền:

1. Kiểm tra tài khoản đã chấp nhận vai trò Threads Tester.
2. Ngắt kết nối rồi OAuth lại sau khi đã thêm quyền.
3. Xác minh token chứa `threads_keyword_search`.
4. Kiểm tra App Review nếu App đã phục vụ tài khoản ngoài nhóm tester.

