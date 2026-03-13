import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, date
import json
import os
import shutil

st.set_page_config(
    page_title="Brossard Manager",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "database.db"
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"

BACKUP_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT,
        email TEXT,
        phone TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        owner TEXT,
        status TEXT,
        priority TEXT,
        start_date TEXT,
        end_date TEXT,
        budget_planned REAL DEFAULT 0,
        budget_actual REAL DEFAULT 0,
        description TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER,
        title TEXT NOT NULL,
        assigned_to TEXT,
        status TEXT,
        priority TEXT,
        start_date TEXT,
        due_date TEXT,
        cost_planned REAL DEFAULT 0,
        cost_actual REAL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(project_id) REFERENCES projects(id)
    )
    """)

    conn.commit()
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    if fetch:
        rows = cur.fetchall()
        conn.close()
        return rows
    conn.close()
    return None

def create_backup():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    db_backup_file = BACKUP_DIR / f"database_backup_{timestamp}.db"
    if DB_PATH.exists():
        shutil.copy(DB_PATH, db_backup_file)

    conn = get_connection()
    staff_df = pd.read_sql_query("SELECT * FROM staff", conn)
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    conn.close()

    backup_json = {
        "staff": staff_df.to_dict(orient="records"),
        "projects": projects_df.to_dict(orient="records"),
        "tasks": tasks_df.to_dict(orient="records"),
        "created_at": timestamp
    }

    json_backup_file = BACKUP_DIR / f"backup_{timestamp}.json"
    with open(json_backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_json, f, indent=4, ensure_ascii=False)

    return db_backup_file.name, json_backup_file.name

def export_data():
    conn = get_connection()
    staff_df = pd.read_sql_query("SELECT * FROM staff", conn)
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    conn.close()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    staff_file = EXPORT_DIR / f"staff_{timestamp}.csv"
    projects_file = EXPORT_DIR / f"projects_{timestamp}.csv"
    tasks_file = EXPORT_DIR / f"tasks_{timestamp}.csv"

    staff_df.to_csv(staff_file, index=False)
    projects_df.to_csv(projects_file, index=False)
    tasks_df.to_csv(tasks_file, index=False)

    return staff_file.name, projects_file.name, tasks_file.name

init_db()

st.sidebar.title("⚽ Brossard Manager")
menu = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Staff", "Projects", "Tasks", "Budget", "Backups"]
)

if menu == "Dashboard":
    st.title("Dashboard")

    conn = get_connection()
    staff_df = pd.read_sql_query("SELECT * FROM staff", conn)
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    conn.close()

    total_projects = len(projects_df)
    total_tasks = len(tasks_df)
    total_staff = len(staff_df)

    budget_planned = projects_df["budget_planned"].sum() if not projects_df.empty else 0
    budget_actual = projects_df["budget_actual"].sum() if not projects_df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projetos", total_projects)
    c2.metric("Tarefas", total_tasks)
    c3.metric("Funcionários", total_staff)
    c4.metric("Budget total", f"${budget_planned:,.2f}")

    c5, c6 = st.columns(2)
    c5.metric("Gasto real", f"${budget_actual:,.2f}")
    c6.metric("Saldo", f"${(budget_planned - budget_actual):,.2f}")

    st.subheader("Projetos")
    if not projects_df.empty:
        st.dataframe(projects_df, use_container_width=True)
    else:
        st.info("Nenhum projeto registado ainda.")

    st.subheader("Tarefas")
    if not tasks_df.empty:
        st.dataframe(tasks_df, use_container_width=True)
    else:
        st.info("Nenhuma tarefa registada ainda.")

elif menu == "Staff":
    st.title("Staff")

    with st.form("staff_form"):
        st.subheader("Adicionar funcionário")
        col1, col2 = st.columns(2)
        name = col1.text_input("Nome")
        role = col2.text_input("Função")
        email = col1.text_input("Email")
        phone = col2.text_input("Telefone")
        submitted = st.form_submit_button("Guardar funcionário")

        if submitted and name:
            run_query(
                "INSERT INTO staff (name, role, email, phone) VALUES (?, ?, ?, ?)",
                (name, role, email, phone)
            )
            st.success("Funcionário adicionado com sucesso.")

    conn = get_connection()
    staff_df = pd.read_sql_query("SELECT * FROM staff", conn)
    conn.close()

    st.subheader("Lista do staff")
    st.dataframe(staff_df, use_container_width=True)

elif menu == "Projects":
    st.title("Projetos")

    staff_names = [row[0] for row in run_query("SELECT name FROM staff", fetch=True)]
    categories = ["Technique", "Compétitif", "CDC", "Camps", "Formation", "Administration", "Événements", "Voyages", "Finance", "Communication"]
    statuses = ["Idée", "En préparation", "En cours", "Terminé", "Annulé"]
    priorities = ["Haute", "Moyenne", "Basse"]

    with st.form("project_form"):
        st.subheader("Criar projeto")
        col1, col2, col3 = st.columns(3)

        name = col1.text_input("Nome do projeto")
        category = col2.selectbox("Categoria", categories)
        owner = col3.selectbox("Responsável", staff_names if staff_names else [""])

        status = col1.selectbox("Status", statuses)
        priority = col2.selectbox("Prioridade", priorities)
        start_date = col3.date_input("Data início", value=date.today())

        end_date = col1.date_input("Data fim", value=date.today())
        budget_planned = col2.number_input("Budget previsto", min_value=0.0, step=100.0)
        budget_actual = col3.number_input("Budget real", min_value=0.0, step=100.0)

        description = st.text_area("Descrição")
        submitted = st.form_submit_button("Guardar projeto")

        if submitted and name:
            run_query("""
                INSERT INTO projects
                (name, category, owner, status, priority, start_date, end_date, budget_planned, budget_actual, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, category, owner, status, priority,
                str(start_date), str(end_date),
                budget_planned, budget_actual, description
            ))
            st.success("Projeto criado com sucesso.")

    conn = get_connection()
    projects_df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    conn.close()

    st.subheader("Lista de projetos")
    st.dataframe(projects_df, use_container_width=True)

elif menu == "Tasks":
    st.title("Tarefas")

    conn = get_connection()
    projects_df = pd.read_sql_query("SELECT id, name FROM projects", conn)
    staff_df = pd.read_sql_query("SELECT name FROM staff", conn)
    conn.close()

    project_options = {}
    if not projects_df.empty:
        project_options = {row["name"]: row["id"] for _, row in projects_df.iterrows()}

    staff_names = staff_df["name"].tolist() if not staff_df.empty else []

    statuses = ["À faire", "En cours", "Bloqué", "Terminé"]
    priorities = ["Haute", "Moyenne", "Basse"]

    with st.form("task_form"):
        st.subheader("Criar tarefa")
        col1, col2, col3 = st.columns(3)

        project_name = col1.selectbox("Projeto", list(project_options.keys()) if project_options else [""])
        title = col2.text_input("Título da tarefa")
        assigned_to = col3.selectbox("Responsável", staff_names if staff_names else [""])

        status = col1.selectbox("Status", statuses)
        priority = col2.selectbox("Prioridade", priorities)
        start_date = col3.date_input("Data início", value=date.today(), key="task_start")

        due_date = col1.date_input("Prazo", value=date.today(), key="task_due")
        cost_planned = col2.number_input("Custo previsto", min_value=0.0, step=10.0)
        cost_actual = col3.number_input("Custo real", min_value=0.0, step=10.0)

        notes = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar tarefa")

        if submitted and title and project_name:
            project_id = project_options[project_name]
            run_query("""
                INSERT INTO tasks
                (project_id, title, assigned_to, status, priority, start_date, due_date, cost_planned, cost_actual, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id, title, assigned_to, status, priority,
                str(start_date), str(due_date),
                cost_planned, cost_actual, notes
            ))
            st.success("Tarefa criada com sucesso.")

    conn = get_connection()
    tasks_df = pd.read_sql_query("""
        SELECT
            tasks.id,
            projects.name AS project_name,
            tasks.title,
            tasks.assigned_to,
            tasks.status,
            tasks.priority,
            tasks.start_date,
            tasks.due_date,
            tasks.cost_planned,
            tasks.cost_actual,
            tasks.notes
        FROM tasks
        LEFT JOIN projects ON tasks.project_id = projects.id
        ORDER BY tasks.id DESC
    """, conn)
    conn.close()

    st.subheader("Lista de tarefas")
    st.dataframe(tasks_df, use_container_width=True)

elif menu == "Budget":
    st.title("Budget")

    conn = get_connection()
    projects_df = pd.read_sql_query("""
        SELECT
            id,
            name,
            category,
            owner,
            budget_planned,
            budget_actual,
            (budget_planned - budget_actual) AS balance
        FROM projects
        ORDER BY id DESC
    """, conn)
    conn.close()

    if not projects_df.empty:
        st.dataframe(projects_df, use_container_width=True)

        total_planned = projects_df["budget_planned"].sum()
        total_actual = projects_df["budget_actual"].sum()
        total_balance = projects_df["balance"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Budget previsto total", f"${total_planned:,.2f}")
        c2.metric("Gasto real total", f"${total_actual:,.2f}")
        c3.metric("Saldo total", f"${total_balance:,.2f}")
    else:
        st.info("Nenhum projeto com budget ainda.")

elif menu == "Backups":
    st.title("Backups e Exportação")

    st.subheader("Criar backup agora")
    if st.button("Criar backup completo"):
        db_file, json_file = create_backup()
        st.success(f"Backup criado: {db_file} e {json_file}")

    st.subheader("Exportar dados para CSV")
    if st.button("Exportar CSV"):
        s, p, t = export_data()
        st.success(f"Exportados: {s}, {p}, {t}")

    st.subheader("Ficheiros de backup")
    backup_files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    if backup_files:
        for f in backup_files:
            st.write(f)
    else:
        st.info("Nenhum backup criado ainda.")

    st.subheader("Ficheiros exportados")
    export_files = sorted(os.listdir(EXPORT_DIR), reverse=True)
    if export_files:
        for f in export_files:
            st.write(f)
    else:
        st.info("Nenhuma exportação criada ainda.")
