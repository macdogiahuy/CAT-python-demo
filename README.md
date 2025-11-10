[![CI - Python tests](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml)

## Adaptive Testing (CAT) — mô tả và hướng dẫn sử dụng (phiên bản khớp code hiện tại)

Tài liệu này mô tả cách triển khai CAT trong repository, các file quan trọng, cách chạy service và test nhanh trên máy Windows.

---

## Tóm tắt ngắn

Project này triển khai một service CAT (Computerized Adaptive Testing) sử dụng mô hình IRT 3PL (a, b, c). Bộ core gồm:

- Lựa chọn item dựa trên Fisher information (chọn top-K rồi random 1 trong top-K để tránh quá lặp).
- Ước lượng năng lực θ bằng `catsim.estimation.NumericalSearchEstimator` khi có đủ lịch sử, và dùng fallback heuristic (±0.2–0.3) khi lịch sử quá ngắn hoặc estimator lỗi.

Các endpoints chính được cung cấp bởi `cat_service_api.py` (Flask):

- `POST /api/cat/next-question` — nhận `user_id`, `course_id`, `assignment_id`, `answered_questions`, `last_response`, `current_theta` (tùy); trả về câu hỏi tiếp theo và `temp_theta`.
- `POST /api/cat/submit` — submit toàn bộ bài, tính `final_theta`, lưu `CAT_Results`, và cập nhật `UserAbilities` với smoothing alpha.

---

## File chính và vai trò

- `cat_service_api.py` — Flask service, chứa:

  - Hàm IRT: `irt_prob(a,b,c,theta)` (3PL) và `item_information(item,theta)` (Fisher information).
  - `estimate_theta(...)` — dùng `NumericalSearchEstimator` hoặc fallback heuristic.
  - DB helpers: tạo bảng (nếu cần) và lưu `CAT_Logs`, `CAT_Results`, `UserAbilities`.

- `cat_service_sqlserver_auto.py` — script mô phỏng CAT bằng thư viện `catsim` (Simulator). Dùng để thử nghiệm chiến lược selection/estimation.

- `add_question_DB.py` — script import câu hỏi từ JSON vào `McqQuestions` và `McqChoices`.

- `tts_irt.py` — module helper thuần-Python (được thêm để phục vụ unit test) chứa `irt_prob` và `item_information` sao cho tests có thể chạy độc lập.

- `requirements.txt` — phụ thuộc tối thiểu.

- `tests/` — chứa unit tests:
  - `tests/test_irt.py` — test hàm IRT thuần.
  - `tests/test_estimate_theta.py` — test fallback của `estimate_theta` (không import trực tiếp toàn bộ module service; test dùng AST để load hàm một cách an toàn).

---

## Cấu trúc DB cần có (tối thiểu)

- `dbo.McqQuestions` — cột cần: `Id`, `Content`, `AssignmentId`, `ParamA`, `ParamB`, `ParamC`.
- `dbo.McqChoices` — `Id`, `Content`, `IsCorrect`, `McqQuestionId`.
- `dbo.UserAbilities` — `UserId`, `CourseId`, `Theta`, `LastUpdate`.
- `dbo.CAT_Logs` — lưu lịch sử từng phản hồi cùng ThetaBefore/After.
- `dbo.CAT_Results` — lưu kết quả khi submit.

Lưu ý: `cat_service_api.py` sẽ tự tạo các bảng `CAT_Logs`, `UserAbilities`, `CAT_Results` nếu chưa tồn tại (hàm `ensure_tables`).

---

## Hướng dẫn chạy (Windows, PowerShell)

1. Tạo virtualenv và kích hoạt:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Cài dependencies:

```powershell
pip install -r requirements.txt
```

3. Chỉnh chuỗi kết nối SQL Server (nếu cần):

- Mở `cat_service_api.py` và cập nhật `DB_CONN` cho phù hợp (hoặc sửa `cat_service_sqlserver_auto.py` nếu dùng script mô phỏng). Hiện tại code có chuỗi mẫu dùng Windows Authentication hoặc UID/PWD cứng — khuyến nghị tách ra biến môi trường trước khi deploy.

4. Khởi động service:

```powershell
# từ thư mục dự án
python cat_service_api.py
```

Service sẽ in log và lắng nghe trên `0.0.0.0:5000` mặc định.

5. Import câu hỏi (nếu cần):

```powershell
python add_question_DB.py
```

---

## Ví dụ payload (JSON)

- Lấy câu hỏi tiếp theo:

```json
POST /api/cat/next-question
{
	"user_id": "<user-guid>",
	"course_id": "<course-guid>",
	"assignment_id": "<assignment-guid>",
	"answered_questions": ["qid1", "qid2"],
	"last_response": [1],
	"current_theta": 0.0
}
```

- Submit bài:

```json
POST /api/cat/submit
{
	"user_id": "<user-guid>",
	"course_id": "<course-guid>",
	"assignment_id": "<assignment-guid>",
	"answered_questions": ["qid1","qid2","qid3"],
	"responses": [1,0,1],
	"smoothing_alpha": 0.2
}
```

---

## Testing & CI

- Local tests: đã thêm `pytest` tests. Chạy nhanh:

```powershell
# từ thư mục dự án, trong venv
python -m pytest -q
```

- CI: workflow `.github/workflows/ci-tests.yml` chạy pytest trên push/PR. Badge CI xuất hiện ở đầu README.

## Ghi chú: tests bao gồm test IRT đơn giản và tests cho fallback của `estimate_theta`. Để tránh side-effect khi import `cat_service_api.py` (kết nối DB, engine), test fallback dùng AST/execution để trích hàm `estimate_theta` vào namespace an toàn.
