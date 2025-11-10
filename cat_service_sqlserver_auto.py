import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyodbc
from catsim.estimation import NumericalSearchEstimator
from catsim.initialization import RandomInitializer
from catsim.selection import MaxInfoSelector
from catsim.simulation import Simulator
from catsim.stopping import MaxItemStopper

# ====== 1. Kết nối SQL Server ======
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=CourseHubDB;"
    "UID=sa;"
    "PWD=01012003;"
    "TrustServerCertificate=yes;"
)
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

assignment_id = "88EFC206-674E-4E0B-BFF2-46611A3DD84D"

# ====== 2. Lấy dữ liệu câu hỏi từ DB ======
query = f"""
SELECT ParamA, ParamB, ParamC, 1.0 AS D
FROM dbo.McqQuestions
WHERE AssignmentId = '{assignment_id}'
ORDER BY NEWID() -- random order
"""
df = pd.read_sql(query, conn)

if df.empty:
    raise ValueError("⚠️ Không có câu hỏi nào trong assignment này! Hãy kiểm tra lại DB.")

items = df.to_numpy()
print(f"✅ Loaded {len(items)} questions from assignment '{assignment_id}'")

# ====== 3. Cấu hình mô hình CAT ======
initializer = RandomInitializer()
selector = MaxInfoSelector()
estimator = NumericalSearchEstimator()
stopper = MaxItemStopper(25)   # dừng sau 25 câu

# ====== 4. Mô phỏng thí sinh có năng lực thật θ = 0.8 ======
true_theta = np.array([0.8])
sim = Simulator(items, true_theta, initializer, selector, estimator, stopper)

print("\n🚀 Running CAT simulation...\n")
sim.simulate()
print("\n✅ CAT simulation finished.\n")

# ====== 5. Phân tích kết quả ======
theta_history = sim.estimations[0]
theta_final = theta_history[-1]
questions_used = sim.administered_items[0]
responses = sim.response_vectors[0]

print("📊 --- KẾT QUẢ CUỐI ---")
print(f"Số câu hỏi đã làm: {len(questions_used)}")
print(f"Năng lực thật: {true_theta[0]:.2f}")
print(f"Năng lực ước tính cuối: {theta_final:.4f}\n")

print("📋 --- LỊCH SỬ TỪNG CÂU ---")
for i, qid in enumerate(questions_used):
    response = "Đúng" if responses[i] else "Sai "
    print(f"Câu {i+1:2d}: a={items[qid][0]:.2f}, b={items[qid][1]:.2f}, c={items[qid][2]:.2f} -> {response} | θ sau câu này: {theta_history[i+1]:.3f}")

# ====== 6. Biểu đồ quá trình ước lượng năng lực ======
plt.figure(figsize=(8, 5))
plt.plot(theta_history, marker='o', linestyle='-', linewidth=1.5)
plt.axhline(y=true_theta[0], color='r', linestyle='--', label=f"True θ = {true_theta[0]}")
plt.title("CAT Simulation — Ability Estimation over Time")
plt.xlabel("Câu hỏi thứ #")
plt.ylabel("Giá trị ước lượng θ")
plt.legend()
plt.grid(True)
plt.show()

conn.close()
