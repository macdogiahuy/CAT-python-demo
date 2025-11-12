[![CI - Python tests](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml)

# CAT-python-demo — hướng dẫn chi tiết cho người mới

Mục tiêu: tài liệu này giúp người không quen với CAT/IRT hiểu cách repository hoạt động, cách chạy demo, cách kiểm tra chất lượng item và cách diễn giải kết quả. Nội dung được tổ chức theo thứ tự từ thực hành nhanh (Quickstart) đến lý thuyết và troubleshooting.

---

## Quickstart (bắt đầu nhanh — PowerShell)

1. Mở PowerShell trong thư mục dự án và tạo virtualenv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
# nếu muốn chạy tests (nếu chưa cài pytest):
python -m pip install pytest
```

2. Tạo dữ liệu phản hồi mô phỏng 3PL (mẫu có sẵn trong `scripts`):

```powershell
python scripts\generate_3pl_responses.py --n_respondents 500 --out data\simulated_responses_3pl.csv
# -> tạo data\simulated_responses_3pl.csv
```

3. Chạy công cụ đánh giá item (offline):

```powershell
python eval_items.py --responses data\simulated_responses_3pl.csv --bank data\Java_Course_150_questions.json --out data\eval_java_3pl
```

4. Mở kết quả trong `data\eval_java_3pl`:

- `item_stats.csv` — thống kê item
- `distractors.json` — phân bố đáp án nếu responses là letter-coded
- `corr_report.json` — tương quan giữa params (a/b/c) và thống kê thực nghiệm

---

## Tại sao repo này hữu ích (ý tưởng ngắn gọn)

- Dùng IRT (3PL) để mô tả mối quan hệ giữa năng lực ẩn (theta) và xác suất trả lời đúng một item.
- Hệ thống cho phép mô phỏng responses, đánh giá chất lượng item (p-value, point-biserial, Cronbach alpha), và chạy thử luồng CAT thông qua `cat_service_api.py`.

---

## Glossary (giải thích ngắn, dễ hiểu)

- IRT: mô hình dùng để mô tả xác suất trả lời đúng dựa trên năng lực ẩn và tham số item.
- 3PL (3-parameter logistic): model với a (discrimination), b (difficulty), c (guessing).
- Theta (θ): năng lực ẩn của người thi (thường chuẩn hóa, ví dụ ~N(0,1)).
- p-value (item): tỉ lệ người đúng câu hỏi (proportion correct).
- Point-biserial (r_pb): tương quan giữa đúng item và tổng điểm (thể hiện discrimination thực nghiệm).
- Cronbach alpha: đo độ nhất quán nội bộ của bài kiểm tra.
- Fisher information: lượng thông tin item cung cấp về θ tại một điểm θ.

---

## Dữ liệu — định dạng và ví dụ

1. Bank JSON: mỗi item là một object, ví dụ tối giản:

```json
{
  "id": "Q_001",
  "question": "What is 2+2?",
  "options": ["1", "2", "3", "4"],
  "answer": "D",
  "difficulty": "Easy",
  "param_a": 1.2,
  "param_b": 0.3,
  "param_c": 0.2
}
```

2. Responses CSV: dạng nhị phân (1/0) hoặc letter-coded (A/B/C/D). Ví dụ header có thể là `user_id,Q_001,Q_002,...`.

-- Nếu letter-coded, `eval_items.py` sẽ sinh `distractors.json` để phân tích từng đáp án.

---

## Chạy `eval_items.py` và cách đọc kết quả

Command mẫu:

```powershell
python eval_items.py --responses <path_to_csv> --bank <path_to_bank.json> --out <out_dir>
```

Output chính:

- `<out_dir>/item_stats.csv` — mỗi item: `id, p_value, point_biserial, param_a, param_b, param_c, flags`.
- `<out_dir>/distractors.json` — tần suất lựa chọn cho từng choice (nếu letter-coded).
- `<out_dir>/corr_report.json` — tương quan a vs r_pb, b vs p_value, v.v.

Ví dụ cách diễn giải nhanh:

- `p_value=0.85`: item khá dễ; nếu >0.9 có thể flag `too_easy`.
- `point_biserial=0.15`: discrimination thấp; có thể flag `low_discrimination` nếu <0.2.
- Cronbach alpha toàn bài: nếu <0.5 thì bài kém nhất quán; 0.6–0.8 trung bình; >0.8 tốt.

---

## Các script hữu ích đã có sẵn

- `scripts/generate_3pl_responses.py` — mô phỏng responses theo 3PL (theta~N(0,1)).
- `scripts/generate_sim_responses.py` — mô phỏng đơn giản (ví dụ dùng p cố định) — chỉ để thử pipeline (không thực tế để kiểm tra reliability).
- `eval_items.py` — công cụ offline để tính p-values, r_pb, Cronbach alpha, distractor analysis, correlation report.
- `cat_service_api.py` — Flask demo API cho luồng CAT (lấy câu hỏi tiếp theo / submit kết quả).

---

## Cách test repository (pytest)

1. Trong venv, cài `pytest` nếu chưa có:

```powershell
python -m pip install pytest
```

2. Chạy tests (file kiểm tra JSON banks đã được thêm):

```powershell
python -m pytest -q
```

Gợi ý: test `tests/test_validate_data.py` kiểm tra từng JSON trong `data/` có load được và có các trường cần thiết.

---

## Mẹo để cải thiện "độ chính xác" (practical tips)

1. Dữ liệu mô phỏng phải chứa biến thiên năng lực (theta) — nếu responses được tạo cố định theo p, Cronbach alpha thường thấp.
2. Dùng mô phỏng 3PL với n >= 200–500 để có ước lượng p và r_pb ổn định.
3. Loại bỏ item có `param_a` quá nhỏ (ví dụ a < 0.3) hoặc `param_c` không hợp lý (c quá lớn) sau khi kiểm tra `item_stats.csv`.
4. Nếu muốn phân tích distractor, dùng letter-coded responses (A/B/C/D) để có tần suất lựa chọn mỗi đáp án.

---

## Troubleshooting nhanh

- Nếu `eval_items.py` không khớp id giữa CSV và bank: kiểm tra header và định dạng id của items.
- Nếu `pytest` báo lỗi import: chắc venv chưa active hoặc thiếu packages — dùng `python -m pip install -r requirements.txt`.
- Nếu service không kết nối DB: thử chạy service ở chế độ đọc bank từ file JSON để debug logic trước.

---

## Next steps đề xuất (tôi có thể làm giúp)

1. Chạy mô phỏng 3PL + `eval_items.py` và tóm tắt các item bị flag (tôi có thể tự chạy và báo lại kết quả).
2. Chỉnh generator để xuất letter-coded responses và phân tích distractors.
3. Thêm script nhỏ để calibrate a/b/c từ dữ liệu thực (dùng `pyirt` hoặc gọi R `mirt`).

---

Nếu bạn muốn tôi thực hiện bước nào (ví dụ: A = tóm tắt item flagged, B = tạo letter-coded responses, C = chạy pytest ở môi trường này), hãy chọn — tôi sẽ chạy tiếp và báo kết quả.
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

[![CI - Python tests](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/macdogiahuy/CAT-python-demo/actions/workflows/ci-tests.yml)

## Tổng quan về CAT (Computerized Adaptive Testing)

Tài liệu này giải thích kiến thức chính về CAT, cách hệ thống trong repository hoạt động, cách chạy/test và các mẹo để cải thiện "độ chính xác" (tức là sự hợp lý của ước lượng năng lực và độ ổn định thống kê).

Nội dung chính:

- Kiến thức IRT & 3PL (a, b, c)
- Thuật toán chọn item (information, exposure control)
- Ước lượng năng lực (MLE / MAP / EAP / numerical search)
- Kiểm thử dữ liệu (JSON/CSV) và cách chạy `eval_items.py` để đánh giá item
- Công cụ mô phỏng (scripts) và hướng dẫn chạy trên Windows (PowerShell)

---

## 1. Tóm tắt lý thuyết ngắn

- IRT 3PL: xác suất thí sinh đúng một item được mô tả bởi hàm 3PL:

  $$P(\theta) = c + \frac{1-c}{1 + e^{-a(\theta - b)}}$$

  - a (discrimination): độ phân biệt của item
  - b (difficulty): vị trí khả năng (theta) tại đó P ≈ (1+c)/2
  - c (guessing): xác suất đoán đúng khi theta rất thấp

- Fisher information cho item i tại theta:

  $$I_i(\theta) = \frac{[P'_i(\theta)]^2}{P_i(\theta) (1 - P_i(\theta))}$$

  Việc lựa chọn item dựa trên thông tin (max information) giúp thu thập nhiều thông tin nhất về θ hiện tại.

---

## 2. Kiến trúc và flow của repository (tóm tắt)

- `cat_service_api.py` — Flask API endpoint để lấy câu hỏi tiếp theo (`/api/cat/next-question`) và submit bài (`/api/cat/submit`).

  - Thứ tự xử lý khi client gọi `next-question`:
    1. Tải item pool (từ DB hoặc file JSON tạm thời).
    2. Ước lượng `theta` hiện tại (MAP/MLE/EAP hoặc fallback heuristic nếu ít dữ liệu).
    3. Tính thông tin Fisher cho từng item chưa được trả lời ở `theta` hiện tại.
    4. Áp dụng cơ chế kiểm soát (loại bỏ items bị quá lạm dụng, content balancing).
    5. Chọn top-K theo thông tin rồi random 1 item trong top-K (randomization giảm exposure).
    6. Trả về item (kèm `temp_theta` và meta để client render).

- `eval_items.py` — công cụ offline để đánh giá quality của item bank bằng dữ liệu phản hồi (CSV). Sinh ra `item_stats.csv`, `distractors.json`, `corr_report.json`.

- `scripts/generate_3pl_responses.py` (tạo mẫu 3PL responses) và `scripts/generate_sim_responses.py` (mẫu đơn giản) — tiện để test pipeline và tính các chỉ số.

---

## 3. Các file chính và vai trò cụ thể

- `cat_service_api.py` — service chính (Flask). Chứa:

  - Hàm IRT (3PL) và hàm tính Fisher information.
  - `estimate_theta(...)` (dùng numerical search hoặc fallback)
  - Lưu log và kết quả vào DB (bảng `CAT_Logs`, `CAT_Results`, `UserAbilities` được tự tạo nếu cần).

- `eval_items.py` — đánh giá offline: chấp nhận `--responses` (CSV) và `--bank` (bank JSON) và xuất report. Dùng để kiểm tra p-value, point-biserial, Cronbach alpha và tương quan giữa params và stats.

- `tests/` — unit tests nhỏ:
  - `tests/test_irt.py` — kiểm tra hàm 3PL và item information.
  - `tests/test_validate_data.py` — (đã thêm) kiểm tra tính hợp lệ các file JSON trong `data/` (tải được, schema cơ bản, trả lời nằm trong options, id duy nhất,...).

---

## 4. Cấu trúc DB (tối thiểu cần biết)

- `McqQuestions` / `dbo.McqQuestions`: Id, Content, AssignmentId, ParamA, ParamB, ParamC
- `McqChoices` / `dbo.McqChoices`: Id, Content, IsCorrect, McqQuestionId
- `UserAbilities`: UserId, CourseId, Theta, LastUpdate
- `CAT_Logs`: lưu từng phản hồi kèm ThetaBefore/After
- `CAT_Results`: kết quả khi submit

`cat_service_api.py` có helper `ensure_tables()` để tự tạo bảng tối thiểu khi cần.

---

## 5. Chạy, test & đánh giá (Windows / PowerShell)

1. Tạo virtualenv và cài phụ thuộc (một lần):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
```

2. Kiểm tra nhanh các test pytest:

```powershell
python -m pytest -q
```

3. Kiểm tra/validate dữ liệu JSON trong `data/` (test đã thêm):

```powershell
python -m pytest tests/test_validate_data.py::test_data_files_found -q
python -m pytest tests/test_validate_data.py -q
```

4. Chạy `eval_items.py` để đánh giá bank với responses CSV:

```powershell
python eval_items.py --responses data\simulated_responses_3pl.csv --bank data\Java_Course_150_questions.json --out data\eval_java_3pl
```

Outputs: `item_stats.csv`, `distractors.json`, `corr_report.json` trong folder `--out`.

5. Khởi chạy service (nếu muốn chạy API):

```powershell
# trong venv
python cat_service_api.py
```

Endpoints (JSON):

- `POST /api/cat/next-question` — payload: user_id, course_id, assignment_id, answered_questions, last_response, current_theta
- `POST /api/cat/submit` — payload: user_id, course_id, assignment_id, answered_questions, responses, smoothing_alpha

---

## 6. Cách test "độ chính xác" và cách cải thiện

1. Hiểu ý nghĩa "độ chính xác":

- Cronbach alpha: chỉ báo độ nhất quán nội bộ (classical), cao khi thí sinh có biến thiên năng lực và item phân biệt tốt.
- Correlation a vs point-biserial: kỳ vọng dương (a cao -> discrimination cao -> point-biserial lớn).
- Correlation b vs p-value: kỳ vọng âm (b lớn -> item khó -> p-value thấp).

2. Vì sao ban đầu bạn thấy độ chính xác thấp?

- Nếu bạn tạo responses ngẫu nhiên với p cố định (không phụ thuộc theta), không có biến thiên giữa người => Cronbach thấp.

3. Cách cải thiện (đã làm và gợi ý thêm):

- Dùng mô phỏng 3PL (đã thêm `scripts/generate_3pl_responses.py`) để tạo responses phụ thuộc theta và item params — điều này tạo ra dữ liệu thực tế hơn và các thống kê khớp với IRT.
- Tăng kích thước mẫu (n respondents) để ước lượng p và r_pb ổn định hơn.
- Kiểm tra item params: loại bỏ/cải biên item có `param_a` quá nhỏ (ví dụ a < 0.3) hoặc `param_c` quá lớn (ví dụ c > 0.3) nếu không mong muốn.
- Cân bằng độ khó (b) trong bank — nếu tất cả item quá dễ hoặc quá khó, ước lượng năng lực kém.
- Sử dụng exposure control: randomize trong top-K, áp thêm quy tắc tối đa tần suất 1 item.
- Thu thập dữ liệu thực tế để calibrate lại a/b/c bằng package IRT (Python/R). Mô phỏng chỉ giúp kiểm tra pipeline.

---

## 7. Đánh giá kết quả `eval_items.py` (gợi ý đọc outputs)

- `item_stats.csv`:

  - `p_value`: tỷ lệ thí sinh đúng item
  - `point_biserial`: tương quan giữa item và tổng điểm (loại bỏ item đó)
  - `flags`: `too_hard`, `too_easy`, `low_discrimination` hoặc `ok` — dùng để lọc/điều chỉnh item

- `distractors.json`: nếu responses là letter-coded, chứa tần suất lựa chọn từng lựa chọn theo cả tổng và nhóm trên/dưới.

- `corr_report.json`: các tương quan a vs r_pb, b vs p — dùng để kiểm tra độ khớp giữa params mô phỏng/ước lượng và tham số đã gán.

---

## 8. Các file/scrip mới hữu ích

- `tests/test_validate_data.py` — kiểm tra schema JSON trong `data/`.
- `scripts/generate_sim_responses.py` — tạo responses nhị phân đơn giản.
- `scripts/generate_3pl_responses.py` — tạo responses theo 3PL (theta~N(0,1)). Dùng để kiểm tra pipeline và cải thiện các chỉ số thống kê.

---

## 9. Troubleshooting nhanh

- Nếu `pytest` không chạy: cài `pytest` vào virtualenv: `python -m pip install pytest`.
- Nếu `eval_items.py` báo không tìm được items: kiểm tra header CSV hoặc dùng positional columns (CSV không cần header nhưng mapping sẽ theo vị trí).
- Nếu service cố kết nối DB thất bại: chỉnh `DB_CONN` hoặc chạy service ở chế độ giả lập (đọc bank từ file JSON) để debug luồng logic trước khi kết nối DB thật.

---

## 10. Next steps đề xuất

1. Thu thập một bộ dữ liệu thật (responses thực) và chạy `eval_items.py` để calibrate lại a/b/c bằng thư viện IRT chuyên dụng.
2. Thêm chức năng MAP/EAP chính xác trong `estimate_theta` (hiện tại repo dùng numerical search + fallback). Gói `pyirt` hoặc gọi R `mirt` có thể giúp.
3. Thêm logging chi tiết khi chọn item để phân tích exposure và content balancing.
4. Nếu cần phân tích distractor, tạo responses letter-coded (mô phỏng hoặc thu thập thực) và chạy `eval_items.py` để sinh `distractors.json`.

---

Nếu bạn muốn, tôi có thể: (a) thêm ví dụ chạy dùng letter-coded responses, (b) mở `data/eval_java_3pl/item_stats.csv` và tóm tắt top flagged items, hoặc (c) bổ sung hướng dẫn calibrate a/b/c bằng một script nhỏ.
