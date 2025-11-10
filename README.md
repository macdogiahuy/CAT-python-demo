## Adaptive Testing (CAT) — Mô tả chi tiết và cách áp dụng trong dự án này

Tài liệu này giải thích thuật toán Adaptive Testing (Computerized Adaptive Testing - CAT) được sử dụng trong project, cách hoạt động, các thành phần dữ liệu và API trong repository, cùng hướng dẫn chạy và mở rộng.

---

## 1) Tổng quan về CAT (bằng ngắn gọn)

CAT là một hệ thống kiểm tra thích nghi: câu hỏi được lựa chọn động cho mỗi thí sinh dựa trên ước lượng năng lực hiện tại (θ). Mục tiêu là chọn các câu hỏi giúp tối đa hóa thông tin về θ, dẫn tới ước lượng chính xác với ít câu hỏi hơn so với bài kiểm tra cố định.

Trong repository này, CAT được triển khai dựa trên mô hình IRT (Item Response Theory) 3-parameter logistic (3PL) cùng với chiến lược chọn câu tối đa hóa thông tin Fisher (Max-Info) và bộ ước lượng số học (NumericalSearchEstimator).

## 2) Hệ số IRT và công thức chính

- Mô hình 3PL: P(θ) = c + (1 - c) / (1 + exp(-1.7 _ a _ (θ - b)))

  - a: hệ số phân biệt (discrimination)
  - b: độ khó (difficulty)
  - c: xác suất đúng khi đoán (guessing)

- Thông tin Fisher cho 3PL (được dùng để xếp hạng mức hữu ích của từng item tại θ hiện tại) là hàm của a, b, c, và θ.

## 3) Luồng chính trong repo — ý tưởng vận hành

1. Lấy θ hiện tại của user (từ bảng `UserAbilities`). Nếu chưa có, khởi tạo θ = 0.
2. Lấy danh sách câu hỏi hợp lệ cho assignment (phải có ParamA/ParamB/ParamC trong DB).
3. Nếu user vừa trả lời 1 câu, cập nhật ước lượng θ bằng hàm ước lượng (numerical search) hoặc một fallback heuristic khi lịch sử quá ngắn.
4. Tính thông tin Fisher của tất cả câu chưa làm ở θ hiện tại, chọn top-K (repo dùng top 3) rồi random chọn 1 trong top-K để tránh lặp lại pattern.
5. Trả câu hỏi tiếp theo về client. Khi user hoàn thành, endpoint submit sẽ tính θ cuối, lưu `CAT_Results`, làm mượt giá trị (smoothing) và cập nhật `UserAbilities`.

## 4) Các file chính liên quan (đã đọc trong repo)

- `cat_service_api.py` — Flask API service (core):

  - Endpoint `/api/cat/next-question` — nhận `user_id`, `course_id`, `assignment_id`, `answered_questions`, `last_response`, `current_theta` (tùy).
    - Trả về câu hỏi tiếp theo (id, nội dung, choices) và `temp_theta` (θ tạm tính hiện tại).
  - Endpoint `/api/cat/submit` — submit toàn bộ bài:
    - Nhận `answered_questions`, `responses`, `smoothing_alpha` (mặc định 0.2).
    - Tính `final_theta`, lưu `CAT_Results`, cập nhật `UserAbilities` bằng cách làm mượt: new_theta = old*(1-alpha) + final*alpha.
  - Hàm quan trọng:
    - `irt_prob(a,b,c,theta)` — xác suất đúng cho 3PL
    - `item_information(item, theta)` — Fisher information
    - `estimate_theta(...)` — sử dụng `catsim.estimation.NumericalSearchEstimator` nếu đủ dữ liệu, hoặc fallback heuristic (±0.2–0.3) khi lịch sử ngắn hoặc error.

- `cat_service_sqlserver_auto.py` — script mô phỏng / batch sử dụng `catsim` (simulator) để chạy thử CAT trên tập câu hỏi lấy từ DB. Dùng `RandomInitializer`, `MaxInfoSelector`, `NumericalSearchEstimator`, `MaxItemStopper` (dừng sau N câu). Dùng để debug, mô phỏng hành vi.

- `add_question_DB.py` — script import câu hỏi từ JSON vào bảng `McqQuestions` và `McqChoices`.

## 5) Cấu trúc dữ liệu & bảng SQL (đã tạo/bảo đảm trong code)

- Bảng `McqQuestions` (ít nhất cần các cột): `Id`, `Content`, `AssignmentId`, `ParamA`, `ParamB`, `ParamC`, (một cột ParamD được gán 1.0 trong code).
- Bảng `McqChoices`: `Id`, `Content`, `IsCorrect`, `McqQuestionId`.
- Bảng `UserAbilities`: lưu θ hiện tại per user/course, đảm bảo unique index trên (UserId, CourseId).
- Bảng `CAT_Logs`: lưu lịch sử từng phản hồi (QuestionId, Response, ThetaBefore, ThetaAfter).
- Bảng `CAT_Results`: lưu kết quả khi submit (FinalTheta, CorrectCount, TotalQuestions...).

## 6) Hướng dẫn cài đặt và chạy (Windows)

1. Tạo virtualenv và cài package (một ví dụ cơ bản):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu repository chưa có `requirements.txt`, tối thiểu cần cài:

```powershell
pip install flask sqlalchemy pandas numpy pyodbc catsim matplotlib
```

2. Cấu hình kết nối SQL Server: trong file `cat_service_api.py` (hoặc `cat_service_sqlserver_auto.py`) có chuỗi `DB_CONN`/`conn_str` hardcoded. Thay đổi `SERVER`, `DATABASE`, `UID`, `PWD` theo môi trường của bạn. Nếu dùng Windows Authentication, giữ `trusted_connection=yes`.

3. Khởi tạo DB/tables tự động: khi chạy `cat_service_api.py`, hàm `ensure_tables()` sẽ tạo các bảng `CAT_Logs`, `UserAbilities`, `CAT_Results` nếu chưa tồn tại.

4. Chạy service:

```powershell
# trong venv
python cat_service_api.py
```

Service sẽ chạy trên `0.0.0.0:5000` theo cấu hình hiện tại.

## 7) Ví dụ payload API

- Gọi lấy câu hỏi tiếp theo:

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

Trả về: `next_question` object với `question_id`, `content`, `choices` và `temp_theta`.

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

Trả về object chứa `final_theta`, `updated_user_theta`, `correct`, `total`.

## 8) Hợp đồng (contract) ngắn gọn của API / thuật toán

- Inputs: `user_id` (GUID), `course_id` (GUID), `assignment_id` (GUID), danh sách `answered_questions` (list of question ids strings), `responses` (list of 0/1), optional `current_theta`.
- Outputs: next question (id, content, choices) hoặc final result khi submit gồm final_theta và thống kê.
- Error modes: thiếu câu hỏi hợp lệ (400), mismatch lengths (400), lỗi server (500).

## 9) Edge cases & lưu ý kỹ thuật

- Lịch sử quá ngắn: repo sử dụng heuristic fallback (±0.2–0.3) khi không đủ câu để chạy estimator. Điều này là bình thường nhưng kém chính xác; bạn có thể thay đổi điểm ngưỡng hoặc lưu nhiều lịch sử hơn.
- Items thiếu ParamA/ParamB/ParamC bị loại.
- Nếu P hoặc Q gần 0 sẽ cho information ~0; code đã có kiểm tra tránh chia cho 0.
- Nếu DB chưa có `UserAbilities`, code tạo mới với θ=0.
- Smoothing alpha (0..1): alpha cao => cập nhật user theta theo kết quả mới nhanh hơn; alpha nhỏ => chậm thay đổi.

## 10) Gợi ý cải tiến và mở rộng (low-risk)

1. Thay MaxInfo + random top-k bằng phương pháp epsilon-greedy hoặc UCB để cân bằng khám phá/khai thác.
2. Lưu thêm lịch sử θ per question để phục vụ phân tích và debugging.
3. Thêm unit tests cho:
   - Hàm `irt_prob` (các giá trị ranh giới)
   - `item_information`
   - `estimate_theta` fallback vs numerical estimator (mock items)
4. Thêm `requirements.txt` và một script `run.sh` / `run.ps1` để khởi động service dễ dàng.
5. Cân nhắc thêm caching câu hỏi cho mỗi assignment để giảm truy vấn DB nhiều lần.

## 11) Kiểm thử nhanh (how to smoke test)

1. Import 1 assignment bằng `add_question_DB.py` (đã có ví dụ JSON trong `data/`).
2. Chạy `cat_service_api.py`.
3. Gửi 1 request `next-question` để nhận câu hỏi.
4. Gửi `submit` với vài câu trả lời giả để xem `final_theta` và cập nhật `UserAbilities`.

## 12) Tóm tắt ngắn gọn

File `cat_service_api.py` là trái tim của triển khai CAT trong repo: nó kết hợp IRT 3PL, Fisher information, numerical estimation và cơ chế logging + smoothing để quản lý năng lực người học. `cat_service_sqlserver_auto.py` là script mô phỏng/batch giúp test chiến lược. `add_question_DB.py` giúp import câu hỏi từ JSON.

Nếu bạn muốn, tôi có thể tiếp tục và: (a) thêm `requirements.txt` tự động từ môi trường hiện tại, (b) viết vài unit tests cho các hàm IRT chính, hoặc (c) tách cấu hình DB ra file `.env` để dễ cấu hình — bạn muốn tôi làm tiếp phần nào?

---

File được tạo tự động dựa trên code hiện có trong repository.
