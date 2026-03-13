import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import datetime, date, timedelta
import json
import os
import shutil

# =========================================================
# CONFIGURATION
# =========================================================
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

# =========================================================
# BASE DE DONNÉES
# =========================================================
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS equipe (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        role TEXT,
        email TEXT,
        telephone TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        categorie TEXT,
        responsable TEXT,
        statut TEXT,
        priorite TEXT,
        date_debut TEXT,
        date_fin TEXT,
        budget_prevu REAL DEFAULT 0,
        budget_reel REAL DEFAULT 0,
        description TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS taches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projet_id INTEGER,
        titre TEXT NOT NULL,
        responsable TEXT,
        statut TEXT,
        priorite TEXT,
        date_debut TEXT,
        date_limite TEXT,
        cout_prevu REAL DEFAULT 0,
        cout_reel REAL DEFAULT 0,
        notes TEXT,
        notification_interne INTEGER DEFAULT 0,
        FOREIGN KEY(projet_id) REFERENCES projets(id)
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

# =========================================================
# OUTILS
# =========================================================
def create_backup():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    db_backup_file = BACKUP_DIR / f"database_backup_{timestamp}.db"
    if DB_PATH.exists():
        shutil.copy(DB_PATH, db_backup_file)

    conn = get_connection()
    equipe_df = pd.read_sql_query("SELECT * FROM equipe", conn)
    projets_df = pd.read_sql_query("SELECT * FROM projets", conn)
    taches_df = pd.read_sql_query("SELECT * FROM taches", conn)
    conn.close()

    backup_json = {
        "equipe": equipe_df.to_dict(orient="records"),
        "projets": projets_df.to_dict(orient="records"),
        "taches": taches_df.to_dict(orient="records"),
        "created_at": timestamp
    }

    json_backup_file = BACKUP_DIR / f"backup_{timestamp}.json"
    with open(json_backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_json, f, indent=4, ensure_ascii=False)

    return db_backup_file.name, json_backup_file.name

def export_data():
    conn = get_connection()
    equipe_df = pd.read_sql_query("SELECT * FROM equipe", conn)
    projets_df = pd.read_sql_query("SELECT * FROM projets", conn)
    taches_df = pd.read_sql_query("SELECT * FROM taches", conn)
    conn.close()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    equipe_file = EXPORT_DIR / f"equipe_{timestamp}.csv"
    projets_file = EXPORT_DIR / f"projets_{timestamp}.csv"
    taches_file = EXPORT_DIR / f"taches_{timestamp}.csv"

    equipe_df.to_csv(equipe_file, index=False)
    projets_df.to_csv(projets_file, index=False)
    taches_df.to_csv(taches_file, index=False)

    return equipe_file.name, projets_file.name, taches_file.name

def charger_donnees():
    conn = get_connection()
    equipe_df = pd.read_sql_query("SELECT * FROM equipe ORDER BY id DESC", conn)
    projets_df = pd.read_sql_query("SELECT * FROM projets ORDER BY id DESC", conn)
    taches_df = pd.read_sql_query("""
        SELECT
            taches.id,
            taches.projet_id,
            projets.nom AS projet,
            taches.titre,
            taches.responsable,
            taches.statut,
            taches.priorite,
            taches.date_debut,
            taches.date_limite,
            taches.cout_prevu,
            taches.cout_reel,
            taches.notes,
            taches.notification_interne
        FROM taches
        LEFT JOIN projets ON taches.projet_id = projets.id
        ORDER BY taches.id DESC
    """, conn)
    conn.close()
    return equipe_df, projets_df, taches_df

def to_date_safe(value):
    try:
        return pd.to_datetime(value)
    except Exception:
        return pd.NaT

# =========================================================
# INITIALISATION
# =========================================================
init_db()

CATEGORIES = [
    "Technique", "Compétitif", "CDC", "Camps", "Formation",
    "Administration", "Événements", "Voyages", "Finance", "Communication"
]
STATUTS_PROJET = [
    "Idée", "En préparation", "En attente", "En cours", "Terminé", "Annulé"
]
STATUTS_TACHE = [
    "À faire", "En cours", "Bloqué", "Terminé"
]
PRIORITES = ["Haute", "Moyenne", "Basse"]

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("⚽ Brossard Manager")
menu = st.sidebar.radio(
    "Navigation",
    [
        "Tableau de bord",
        "Équipe",
        "Projets",
        "Tâches",
        "Calendrier",
        "Chronologie",
        "Budget",
        "Sauvegardes"
    ]
)

equipe_df, projets_df, taches_df = charger_donnees()

# =========================================================
# TABLEAU DE BORD
# =========================================================
if menu == "Tableau de bord":
    st.title("Tableau de bord")

    total_projets = len(projets_df)
    total_taches = len(taches_df)
    total_equipe = len(equipe_df)

    budget_prevu = projets_df["budget_prevu"].sum() if not projets_df.empty else 0
    budget_reel = projets_df["budget_reel"].sum() if not projets_df.empty else 0
    solde = budget_prevu - budget_reel

    taches_en_retard = 0
    taches_cette_semaine = 0

    if not taches_df.empty:
        today = pd.Timestamp(date.today())
        taches_df["date_limite_dt"] = pd.to_datetime(taches_df["date_limite"], errors="coerce")
        taches_en_retard = len(
            taches_df[
                (taches_df["date_limite_dt"] < today) &
                (taches_df["statut"] != "Terminé")
            ]
        )
        fin_semaine = today + pd.Timedelta(days=7)
        taches_cette_semaine = len(
            taches_df[
                (taches_df["date_limite_dt"] >= today) &
                (taches_df["date_limite_dt"] <= fin_semaine)
            ]
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projets actifs", total_projets)
    c2.metric("Tâches", total_taches)
    c3.metric("Équipe", total_equipe)
    c4.metric("Budget prévu", f"{budget_prevu:,.2f} $")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Dépenses réelles", f"{budget_reel:,.2f} $")
    c6.metric("Solde", f"{solde:,.2f} $")
    c7.metric("Tâches en retard", taches_en_retard)
    c8.metric("Échéances 7 jours", taches_cette_semaine)

    st.markdown("### Projets")
    if not projets_df.empty:
        st.dataframe(projets_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun projet enregistré pour le moment.")

    st.markdown("### Tâches prioritaires")
    if not taches_df.empty:
        prior_df = taches_df.copy()
        prior_df["date_limite_dt"] = pd.to_datetime(prior_df["date_limite"], errors="coerce")
        prior_df = prior_df.sort_values(by=["date_limite_dt"], ascending=True)
        st.dataframe(
            prior_df[["projet", "titre", "responsable", "statut", "priorite", "date_limite"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aucune tâche enregistrée.")

# =========================================================
# ÉQUIPE
# =========================================================
elif menu == "Équipe":
    st.title("Équipe")

    with st.form("form_equipe"):
        st.subheader("Ajouter un membre")
        c1, c2 = st.columns(2)
        nom = c1.text_input("Nom")
        role = c2.text_input("Rôle")
        email = c1.text_input("Email")
        telephone = c2.text_input("Téléphone")
        submitted = st.form_submit_button("Enregistrer")

        if submitted and nom:
            run_query(
                "INSERT INTO equipe (nom, role, email, telephone) VALUES (?, ?, ?, ?)",
                (nom, role, email, telephone)
            )
            st.success("Membre ajouté avec succès.")
            st.rerun()

    st.subheader("Liste de l'équipe")
    if not equipe_df.empty:
        st.dataframe(equipe_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun membre ajouté.")

# =========================================================
# PROJETS
# =========================================================
elif menu == "Projets":
    st.title("Projets")

    noms_equipe = equipe_df["nom"].tolist() if not equipe_df.empty else []

    with st.form("form_projet"):
        st.subheader("Créer un projet")
        c1, c2, c3 = st.columns(3)

        nom = c1.text_input("Nom du projet")
        categorie = c2.selectbox("Catégorie", CATEGORIES)
        responsable = c3.selectbox("Responsable", noms_equipe if noms_equipe else [""])

        statut = c1.selectbox("Statut", STATUTS_PROJET)
        priorite = c2.selectbox("Priorité", PRIORITES)
        date_debut = c3.date_input("Date de début", value=date.today())

        date_fin = c1.date_input("Date de fin", value=date.today() + timedelta(days=30))
        budget_prevu = c2.number_input("Budget prévu", min_value=0.0, step=100.0)
        budget_reel = c3.number_input("Budget réel", min_value=0.0, step=100.0)

        description = st.text_area("Description")
        submitted = st.form_submit_button("Créer le projet")

        if submitted and nom:
            run_query("""
                INSERT INTO projets
                (nom, categorie, responsable, statut, priorite, date_debut, date_fin, budget_prevu, budget_reel, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nom, categorie, responsable, statut, priorite,
                str(date_debut), str(date_fin), budget_prevu, budget_reel, description
            ))
            st.success("Projet créé avec succès.")
            st.rerun()

    st.subheader("Liste des projets")
    if not projets_df.empty:
        show_df = projets_df.copy()
        show_df["solde"] = show_df["budget_prevu"] - show_df["budget_reel"]
        st.dataframe(show_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun projet enregistré.")

# =========================================================
# TÂCHES
# =========================================================
elif menu == "Tâches":
    st.title("Tâches")

    projets_options = {}
    if not projets_df.empty:
        projets_options = {row["nom"]: row["id"] for _, row in projets_df.iterrows()}

    noms_equipe = equipe_df["nom"].tolist() if not equipe_df.empty else []

    with st.form("form_tache"):
        st.subheader("Ajouter une tâche")
        c1, c2, c3 = st.columns(3)

        projet_nom = c1.selectbox("Projet", list(projets_options.keys()) if projets_options else [""])
        titre = c2.text_input("Titre de la tâche")
        responsable = c3.selectbox("Responsable", noms_equipe if noms_equipe else [""])

        statut = c1.selectbox("Statut", STATUTS_TACHE)
        priorite = c2.selectbox("Priorité", PRIORITES)
        date_debut = c3.date_input("Date de début", value=date.today(), key="date_debut_tache")

        date_limite = c1.date_input("Date limite", value=date.today() + timedelta(days=7), key="date_limite_tache")
        cout_prevu = c2.number_input("Coût prévu", min_value=0.0, step=10.0)
        cout_reel = c3.number_input("Coût réel", min_value=0.0, step=10.0)

        notes = st.text_area("Notes")
        notification_interne = st.checkbox("Afficher comme notification interne")
        submitted = st.form_submit_button("Enregistrer la tâche")

        if submitted and titre and projet_nom:
            projet_id = projets_options[projet_nom]
            run_query("""
                INSERT INTO taches
                (projet_id, titre, responsable, statut, priorite, date_debut, date_limite, cout_prevu, cout_reel, notes, notification_interne)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                projet_id, titre, responsable, statut, priorite,
                str(date_debut), str(date_limite), cout_prevu, cout_reel, notes, 1 if notification_interne else 0
            ))
            st.success("Tâche ajoutée avec succès.")
            st.rerun()

    st.subheader("Filtrer les tâches")
    f1, f2, f3 = st.columns(3)
    filtre_responsable = f1.selectbox(
        "Responsable",
        ["Tous"] + (sorted(taches_df["responsable"].dropna().unique().tolist()) if not taches_df.empty else [])
    )
    filtre_statut = f2.selectbox(
        "Statut",
        ["Tous"] + STATUTS_TACHE
    )
    filtre_projet = f3.selectbox(
        "Projet",
        ["Tous"] + (sorted(taches_df["projet"].dropna().unique().tolist()) if not taches_df.empty else [])
    )

    filtered = taches_df.copy()
    if not filtered.empty:
        if filtre_responsable != "Tous":
            filtered = filtered[filtered["responsable"] == filtre_responsable]
        if filtre_statut != "Tous":
            filtered = filtered[filtered["statut"] == filtre_statut]
        if filtre_projet != "Tous":
            filtered = filtered[filtered["projet"] == filtre_projet]

        st.dataframe(filtered, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune tâche enregistrée.")

    st.subheader("Notifications internes")
    if not taches_df.empty:
        notif_df = taches_df[taches_df["notification_interne"] == 1]
        if not notif_df.empty:
            st.dataframe(
                notif_df[["projet", "titre", "responsable", "statut", "date_limite"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune notification interne pour le moment.")
    else:
        st.info("Aucune tâche enregistrée.")

# =========================================================
# CALENDRIER
# =========================================================
elif menu == "Calendrier":
    st.title("Calendrier des tâches")

    if taches_df.empty:
        st.info("Aucune tâche pour le moment.")
    else:
        cal_df = taches_df.copy()
        cal_df["date_debut_dt"] = pd.to_datetime(cal_df["date_debut"], errors="coerce")
        cal_df["date_limite_dt"] = pd.to_datetime(cal_df["date_limite"], errors="coerce")

        vue = st.radio("Vue", ["Agenda des échéances", "Calendrier hebdomadaire"], horizontal=True)

        if vue == "Agenda des échéances":
            agenda = cal_df[["date_limite_dt", "projet", "titre", "responsable", "statut", "priorite"]].copy()
            agenda = agenda.sort_values("date_limite_dt")
            agenda["date_limite"] = agenda["date_limite_dt"].dt.strftime("%Y-%m-%d")
            agenda = agenda.drop(columns=["date_limite_dt"])
            st.dataframe(agenda, use_container_width=True, hide_index=True)

        else:
            debut_semaine = st.date_input("Semaine de référence", value=date.today())
            debut_semaine = pd.Timestamp(debut_semaine)
            fin_semaine = debut_semaine + pd.Timedelta(days=6)

            semaine = cal_df[
                (cal_df["date_limite_dt"] >= debut_semaine) &
                (cal_df["date_limite_dt"] <= fin_semaine)
            ].copy()

            if semaine.empty:
                st.info("Aucune tâche prévue pour cette semaine.")
            else:
                semaine["jour"] = semaine["date_limite_dt"].dt.strftime("%A %d/%m")
                semaine["résumé"] = (
                    semaine["titre"] + " | " +
                    semaine["responsable"].fillna("") + " | " +
                    semaine["statut"].fillna("")
                )
                pivot = semaine.groupby("jour")["résumé"].apply(lambda x: " ; ".join(x)).reset_index()
                st.dataframe(pivot, use_container_width=True, hide_index=True)

# =========================================================
# CHRONOLOGIE
# =========================================================
elif menu == "Chronologie":
    st.title("Chronologie des projets et des tâches")

    if projets_df.empty and taches_df.empty:
        st.info("Aucune donnée disponible.")
    else:
        type_vue = st.radio("Type de chronologie", ["Projets", "Tâches"], horizontal=True)

        if type_vue == "Projets":
            if projets_df.empty:
                st.info("Aucun projet disponible.")
            else:
                chrono = projets_df.copy()
                chrono["date_debut"] = pd.to_datetime(chrono["date_debut"], errors="coerce")
                chrono["date_fin"] = pd.to_datetime(chrono["date_fin"], errors="coerce")
                chrono = chrono.dropna(subset=["date_debut", "date_fin"])

                if chrono.empty:
                    st.info("Dates invalides dans les projets.")
                else:
                    fig = px.timeline(
                        chrono,
                        x_start="date_debut",
                        x_end="date_fin",
                        y="nom",
                        color="statut",
                        hover_data=["categorie", "responsable", "priorite"]
                    )
                    fig.update_yaxes(autorange="reversed")
                    fig.update_layout(height=600)
                    st.plotly_chart(fig, use_container_width=True)

        else:
            if taches_df.empty:
                st.info("Aucune tâche disponible.")
            else:
                chrono = taches_df.copy()
                chrono["date_debut"] = pd.to_datetime(chrono["date_debut"], errors="coerce")
                chrono["date_limite"] = pd.to_datetime(chrono["date_limite"], errors="coerce")
                chrono = chrono.dropna(subset=["date_debut", "date_limite"])

                if chrono.empty:
                    st.info("Dates invalides dans les tâches.")
                else:
                    fig = px.timeline(
                        chrono,
                        x_start="date_debut",
                        x_end="date_limite",
                        y="titre",
                        color="statut",
                        hover_data=["projet", "responsable", "priorite"]
                    )
                    fig.update_yaxes(autorange="reversed")
                    fig.update_layout(height=700)
                    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# BUDGET
# =========================================================
elif menu == "Budget":
    st.title("Budget des projets")

    if projets_df.empty:
        st.info("Aucun projet enregistré.")
    else:
        budget_df = projets_df.copy()
        budget_df["solde"] = budget_df["budget_prevu"] - budget_df["budget_reel"]
        budget_df["consommation_%"] = budget_df.apply(
            lambda row: round((row["budget_reel"] / row["budget_prevu"]) * 100, 1)
            if row["budget_prevu"] > 0 else 0,
            axis=1
        )

        st.dataframe(
            budget_df[[
                "nom", "categorie", "responsable", "budget_prevu",
                "budget_reel", "solde", "consommation_%", "statut"
            ]],
            use_container_width=True,
            hide_index=True
        )

        total_prevu = budget_df["budget_prevu"].sum()
        total_reel = budget_df["budget_reel"].sum()
        total_solde = budget_df["solde"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Budget total prévu", f"{total_prevu:,.2f} $")
        c2.metric("Dépenses totales", f"{total_reel:,.2f} $")
        c3.metric("Solde total", f"{total_solde:,.2f} $")

        fig = px.bar(
            budget_df,
            x="nom",
            y=["budget_prevu", "budget_reel"],
            barmode="group",
            title="Comparaison budget prévu vs réel"
        )
        st.plotly_chart(fig, use_container_width=True)

# =========================================================
# SAUVEGARDES
# =========================================================
elif menu == "Sauvegardes":
    st.title("Sauvegardes et exportation")

    st.subheader("Créer une sauvegarde complète")
    if st.button("Créer la sauvegarde maintenant"):
        db_file, json_file = create_backup()
        st.success(f"Sauvegarde créée : {db_file} et {json_file}")

    st.subheader("Exporter les données")
    if st.button("Exporter en CSV"):
        e, p, t = export_data()
        st.success(f"Fichiers exportés : {e}, {p}, {t}")

    st.subheader("Fichiers de sauvegarde")
    backup_files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    if backup_files:
        for f in backup_files:
            st.write(f)
    else:
        st.info("Aucune sauvegarde disponible.")

    st.subheader("Fichiers exportés")
    export_files = sorted(os.listdir(EXPORT_DIR), reverse=True)
    if export_files:
        for f in export_files:
            st.write(f)
    else:
        st.info("Aucune exportation disponible.")
