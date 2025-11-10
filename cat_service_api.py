import random
from types import SimpleNamespace

import numpy as np
import pandas as pd
from catsim.estimation import NumericalSearchEstimator
from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text

# ============================================================
# ⚙️ Kết nối SQL Server
# ============================================================
DB_CONN = (
    "mssql+pyodbc://localhost/CourseHubDB?"
    "driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)
engine = create_engine(DB_CONN, fast_executemany=True)
app = Flask(__name__)

# ============================================================
# 🧱 Đảm bảo bảng cần thiết tồn tại
# ============================================================
def ensure_tables():
    with engine.begin() as conn:
        # ----- 1. CAT_Logs -----
        conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CAT_Logs' AND xtype='U')
        CREATE TABLE dbo.CAT_Logs (
            Id UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
            UserId UNIQUEIDENTIFIER,
            CourseId UNIQUEIDENTIFIER,
            AssignmentId UNIQUEIDENTIFIER,
            QuestionId UNIQUEIDENTIFIER,
            Response BIT,
            ThetaBefore FLOAT,
            ThetaAfter FLOAT,
            Timestamp DATETIME DEFAULT GETDATE()
        )
        """))

        # ----- 2. UserAbilities -----
        conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='UserAbilities' AND xtype='U')
        BEGIN
            CREATE TABLE dbo.UserAbilities (
                Id UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
                UserId UNIQUEIDENTIFIER NOT NULL,
                CourseId UNIQUEIDENTIFIER NOT NULL,
                Theta FLOAT DEFAULT 0,
                LastUpdate DATETIME2 DEFAULT GETDATE()
            );
        END

        IF NOT EXISTS (
            SELECT * FROM sys.indexes WHERE name = 'UQ_UserAbilities'
              AND object_id = OBJECT_ID('dbo.UserAbilities')
        )
        BEGIN
            CREATE UNIQUE INDEX UQ_UserAbilities
            ON dbo.UserAbilities(UserId, CourseId);
        END
        """))

        # ----- 3. CAT_Results -----
        conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CAT_Results' AND xtype='U')
        CREATE TABLE dbo.CAT_Results (
            Id UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
            UserId UNIQUEIDENTIFIER NOT NULL,
            CourseId UNIQUEIDENTIFIER NOT NULL,
            AssignmentId UNIQUEIDENTIFIER NULL,
            FinalTheta FLOAT NOT NULL,
            CorrectCount INT NOT NULL,
            TotalQuestions INT NOT NULL,
            ThetaBefore FLOAT NULL,
            ThetaAfter FLOAT NULL,
            CompletionTime DATETIME2 DEFAULT GETDATE()
        )
        """))

# ============================================================
# 📈 Công thức IRT & ước lượng theta
# ============================================================
def irt_prob(a, b, c, theta):
    """3PL model probability"""
    return c + (1 - c) / (1 + np.exp(-1.7 * a * (theta - b)))

def item_information(item, theta):
    """Fisher information for 3PL model"""
    a, b, c, _ = item
    P = irt_prob(a, b, c, theta)
    Q = 1 - P
    if P <= 0 or Q <= 0 or (1 - c) == 0:
        return 0.0
    return (1.7 * a) ** 2 * ((P - c) ** 2 / ((1 - c) ** 2 * P * Q)) * P * Q

def estimate_theta(items, administered_items, responses, current_theta):
    """Estimate theta with fallback for short history"""
    theta_before = current_theta
    try:
        if not administered_items or len(administered_items) <= 1:
            delta = 0.3 if responses and responses[-1] == 1 else -0.3
            return float(np.clip(current_theta + delta, -4, 4)), theta_before

        est = NumericalSearchEstimator()
        dummy = SimpleNamespace(
            items=np.array(items, dtype=float),
            administered_items=np.array(administered_items, dtype=int),
            response_vectors=[np.array(responses, dtype=int)],
            est_theta=current_theta
        )
        new_theta = est.estimate(
            simulator=dummy,
            items=np.array(items, dtype=float),
            administered_items=np.array(administered_items, dtype=int),
            response_vector=np.array(responses, dtype=int),
            est_theta=current_theta
        )
        return float(np.clip(new_theta, -4, 4)), theta_before
    except Exception as e:
        delta = 0.2 if responses and responses[-1] == 1 else -0.2
        print("⚠️ estimate_theta fallback:", e)
        return float(np.clip(current_theta + delta, -4, 4)), theta_before

# ============================================================
# 🚀 API: /api/cat/next-question
# ============================================================
@app.route('/api/cat/next-question', methods=['POST'])
def next_question():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        course_id = data.get("course_id")
        assignment_id = data.get("assignment_id")
        answered_questions = data.get("answered_questions", [])
        last_response = data.get("last_response", [])
        client_theta = data.get("current_theta", None)

        # --- Lấy hoặc khởi tạo theta tổng thể ---
        with engine.begin() as conn:
            res = conn.execute(text("""
                SELECT Theta FROM dbo.UserAbilities
                WHERE UserId = :u AND CourseId = :c
            """), {"u": user_id, "c": course_id}).scalar()
            if res is None:
                conn.execute(text("""
                    INSERT INTO dbo.UserAbilities (UserId, CourseId, Theta)
                    VALUES (:u, :c, 0.0)
                """), {"u": user_id, "c": course_id})
                current_theta = 0.0
            else:
                current_theta = float(res)

        if client_theta is not None:
            try:
                current_theta = float(client_theta)
            except:
                pass

        # --- Lấy danh sách câu hỏi ---
        df = pd.read_sql(text("""
            SELECT Id, Content, ParamA, ParamB, ParamC
            FROM dbo.McqQuestions
            WHERE AssignmentId = :aid
              AND ParamA IS NOT NULL AND ParamB IS NOT NULL AND ParamC IS NOT NULL
        """), engine, params={"aid": assignment_id})
        if df.empty:
            return jsonify({"error": "No valid questions found."}), 400

        df["Id"] = df["Id"].astype(str)
        df["ParamD"] = 1.0
        all_ids = df["Id"].tolist()
        items = df[["ParamA", "ParamB", "ParamC", "ParamD"]].to_numpy(dtype=float)

        # --- Ước lượng theta mới nếu có phản hồi ---
        if last_response and answered_questions:
            matched = [q for q in answered_questions if q in all_ids]
            administered_items = [all_ids.index(q) for q in matched]
            responses = [int(last_response[-1])]
            theta_after, theta_before = estimate_theta(items, administered_items, responses, current_theta)

            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO dbo.CAT_Logs (UserId, CourseId, AssignmentId, QuestionId, Response, ThetaBefore, ThetaAfter)
                    VALUES (:u, :c, :a, :q, :r, :tb, :ta)
                """), {
                    "u": user_id, "c": course_id, "a": assignment_id,
                    "q": answered_questions[-1], "r": bool(last_response[-1]),
                    "tb": float(current_theta), "ta": float(theta_after)
                })
            current_theta = theta_after

        # --- Lọc câu chưa làm ---
        unanswered_df = df[~df["Id"].isin(answered_questions)].reset_index(drop=True)
        if unanswered_df.empty:
            return jsonify({"message": "✅ All questions completed.", "final_theta": round(current_theta, 3)})

        # --- Chọn câu hỏi kế ---
        unanswered_items = unanswered_df[["ParamA", "ParamB", "ParamC", "ParamD"]].to_numpy(dtype=float)
        info_values = [item_information(item, current_theta) for item in unanswered_items]
        sorted_indices = np.argsort(info_values)[::-1]
        top_k = sorted_indices[:3] if len(sorted_indices) >= 3 else sorted_indices
        next_idx_local = int(random.choice(top_k))
        next_question_row = unanswered_df.iloc[next_idx_local]

        qid = str(next_question_row["Id"])
        choices = pd.read_sql(text("""
            SELECT Id, Content FROM dbo.McqChoices WHERE McqQuestionId = :qid
        """), engine, params={"qid": qid}).to_dict(orient="records")

        return jsonify({
            "next_question": {
                "question_id": qid,
                "content": next_question_row["Content"],
                "choices": choices
            },
            "temp_theta": round(current_theta, 3)
        })

    except Exception as e:
        print("🔥 ERROR /next-question:", e)
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🚀 API: /api/cat/submit
# ============================================================
@app.route('/api/cat/submit', methods=['POST'])
def submit_assignment():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        course_id = data.get("course_id")
        assignment_id = data.get("assignment_id")
        answered_questions = data.get("answered_questions", [])
        responses = data.get("responses", [])
        alpha = float(data.get("smoothing_alpha", 0.2))

        if not answered_questions or not responses or len(answered_questions) != len(responses):
            return jsonify({"error": "answered_questions and responses must match length."}), 400

        df = pd.read_sql(text("""
            SELECT Id, ParamA, ParamB, ParamC
            FROM dbo.McqQuestions
            WHERE AssignmentId = :aid
              AND ParamA IS NOT NULL AND ParamB IS NOT NULL AND ParamC IS NOT NULL
        """), engine, params={"aid": assignment_id})
        if df.empty:
            return jsonify({"error": "No valid questions."}), 400

        df["Id"] = df["Id"].astype(str)
        df["ParamD"] = 1.0
        all_ids = df["Id"].tolist()
        items = df[["ParamA", "ParamB", "ParamC", "ParamD"]].to_numpy(dtype=float)

        with engine.begin() as conn:
            res = conn.execute(text("""
                SELECT Theta FROM dbo.UserAbilities
                WHERE UserId = :u AND CourseId = :c
            """), {"u": user_id, "c": course_id}).scalar()
            user_theta_before = float(res) if res is not None else 0.0

        administered_items = []
        resp_list = []
        for qid, r in zip(answered_questions, responses):
            if qid in all_ids:
                administered_items.append(all_ids.index(qid))
                resp_list.append(int(r))

        final_theta, _ = estimate_theta(items, administered_items, resp_list, user_theta_before)
        correct_count = sum(resp_list)
        total_questions = len(resp_list)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO dbo.CAT_Results (UserId, CourseId, AssignmentId, FinalTheta, CorrectCount, TotalQuestions, ThetaBefore, ThetaAfter)
                VALUES (:u, :c, :a, :ft, :corr, :tot, :tb, :ta)
            """), {
                "u": user_id, "c": course_id, "a": assignment_id,
                "ft": final_theta, "corr": correct_count, "tot": total_questions,
                "tb": user_theta_before, "ta": final_theta
            })

            new_theta = user_theta_before * (1 - alpha) + final_theta * alpha
            updated = conn.execute(text("""
                UPDATE dbo.UserAbilities
                SET Theta = :t, LastUpdate = GETDATE()
                WHERE UserId = :u AND CourseId = :c
            """), {"t": new_theta, "u": user_id, "c": course_id}).rowcount

            if updated == 0:
                conn.execute(text("""
                    INSERT INTO dbo.UserAbilities (UserId, CourseId, Theta)
                    VALUES (:u, :c, :t)
                """), {"u": user_id, "c": course_id, "t": new_theta})

        return jsonify({
            "message": "✅ Assignment submitted successfully.",
            "final_theta": round(final_theta, 3),
            "updated_user_theta": round(new_theta, 3),
            "correct": correct_count,
            "total": total_questions
        })

    except Exception as e:
        print("🔥 ERROR /submit:", e)
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🏁 Run
# ============================================================
if __name__ == "__main__":
    ensure_tables()
    print("🚀 CAT service v2 running on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)