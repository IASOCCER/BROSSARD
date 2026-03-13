import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import datetime, date, timedelta
import json
import os
import shutil
from io import BytesIO

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
    CREATE TABLE IF NOT EXISTS saisons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        categorie TEXT,
        responsable TEXT,
        date_debut TEXT,
        date_fin TEXT,
        statut TEXT,
        notes TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        saison_id INTEGER,
        categorie TEXT,
        responsable TEXT,
        statut TEXT,
        priorite TEXT,
        date_debut TEXT,
        date_fin TEXT,
        budget_prevu REAL DEFAULT 0,
        budget_reel REAL DEFAULT 0,
        revenu_prevu REAL DEFAULT 0,
        revenu_reel REAL DEFAULT 0,
        description TEXT,
        FOREIGN KEY(saison_id) REFERENCES saisons(id)
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS budget_lignes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projet_id INTEGER,
        type_ligne TEXT DEFAULT 'Dépense',
        categorie TEXT,
        description TEXT,
        quantite REAL DEFAULT 1,
        montant_unitaire_prevu REAL DEFAULT 0,
        montant_unitaire_reel REAL DEFAULT 0,
        total_prevu REAL DEFAULT 0,
        total_reel REAL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(projet_id) REFERENCES projets(id)
    )
    """)

    # Migrations douces
    colonnes_projets = [row[1] for row in cur.execute("PRAGMA table_info(projets)").fetchall()]
    if "revenu_prevu" not in colonnes_projets:
        cur.execute("ALTER TABLE projets ADD COLUMN revenu_prevu REAL DEFAULT 0")
    if "revenu_reel" not in colonnes_projets:
        cur.execute("ALTER TABLE projets ADD COLUMN revenu_reel REAL DEFAULT 0")
    if "saison_id" not in colonnes_projets:
        cur.execute("ALTER TABLE projets ADD COLUMN saison_id INTEGER")

    colonnes_budget = [row[1] for row in cur.execute("PRAGMA table_info(budget_lignes)").fetchall()]
    if "type_ligne" not in colonnes_budget:
        cur.execute("ALTER TABLE budget_lignes ADD COLUMN type_ligne TEXT DEFAULT 'Dépense'")
    if "montant_unitaire_prevu" not in colonnes_budget and "cout_unitaire_prevu" in colonnes_budget:
        cur.execute("ALTER TABLE budget_lignes ADD COLUMN montant_unitaire_prevu REAL DEFAULT 0")
        cur.execute("UPDATE budget_lignes SET montant_unitaire_prevu = cout_unitaire_prevu")
    if "montant_unitaire_reel" not in colonnes_budget and "cout_unitaire_reel" in colonnes_budget:
        cur.execute("ALTER TABLE budget_lignes ADD COLUMN montant_unitaire_reel REAL DEFAULT 0")
        cur.execute("UPDATE budget_lignes SET montant_unitaire_reel = cout_unitaire_reel")

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
# DONNÉES / CALCULS
# =========================================================
def recalculer_finances_projets():
    conn = get_connection()
    projets = pd.read_sql_query("SELECT id FROM projets", conn)

    for _, row in projets.iterrows():
        projet_id = row["id"]
        lignes = pd.read_sql_query(
            "SELECT type_ligne, total_prevu, total_reel FROM budget_lignes WHERE projet_id = ?",
            conn,
            params=(projet_id,)
        )

        dep_prevu = lignes[lignes["type_ligne"] == "Dépense"]["total_prevu"].sum() if not lignes.empty else 0
        dep_reel = lignes[lignes["type_ligne"] == "Dépense"]["total_reel"].sum() if not lignes.empty else 0
        rev_prevu = lignes[lignes["type_ligne"] == "Revenu"]["total_prevu"].sum() if not lignes.empty else 0
        rev_reel = lignes[lignes["type_ligne"] == "Revenu"]["total_reel"].sum() if not lignes.empty else 0

        conn.execute(
            """
            UPDATE projets
            SET budget_prevu = ?, budget_reel = ?, revenu_prevu = ?, revenu_reel = ?
            WHERE id = ?
            """,
            (float(dep_prevu), float(dep_reel), float(rev_prevu), float(rev_reel), int(projet_id))
        )

    conn.commit()
    conn.close()

def charger_donnees():
    conn = get_connection()

    equipe_df = pd.read_sql_query("SELECT * FROM equipe ORDER BY id DESC", conn)
    saisons_df = pd.read_sql_query("SELECT * FROM saisons ORDER BY id DESC", conn)

    projets_df = pd.read_sql_query("""
        SELECT
            projets.*,
            saisons.nom AS saison_nom
        FROM projets
        LEFT JOIN saisons ON projets.saison_id = saisons.id
        ORDER BY projets.id DESC
    """, conn)

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

    budget_lignes_df = pd.read_sql_query("""
        SELECT
            budget_lignes.id,
            budget_lignes.projet_id,
            projets.nom AS projet,
            budget_lignes.type_ligne,
            budget_lignes.categorie,
            budget_lignes.description,
            budget_lignes.quantite,
            budget_lignes.montant_unitaire_prevu,
            budget_lignes.montant_unitaire_reel,
            budget_lignes.total_prevu,
            budget_lignes.total_reel,
            budget_lignes.notes
        FROM budget_lignes
        LEFT JOIN projets ON budget_lignes.projet_id = projets.id
        ORDER BY budget_lignes.id DESC
    """, conn)

    conn.close()
    return equipe_df, saisons_df, projets_df, taches_df, budget_lignes_df

# =========================================================
# EXPORT / BACKUP
# =========================================================
def generate_backup_files():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    conn = get_connection()
    equipe_df = pd.read_sql_query("SELECT * FROM equipe", conn)
    saisons_df = pd.read_sql_query("SELECT * FROM saisons", conn)
    projets_df = pd.read_sql_query("SELECT * FROM projets", conn)
    taches_df = pd.read_sql_query("SELECT * FROM taches", conn)
    budget_df = pd.read_sql_query("SELECT * FROM budget_lignes", conn)
    conn.close()

    backup_json = {
        "created_at": timestamp,
        "equipe": equipe_df.to_dict(orient="records"),
        "saisons": saisons_df.to_dict(orient="records"),
        "projets": projets_df.to_dict(orient="records"),
        "taches": taches_df.to_dict(orient="records"),
        "budget_lignes": budget_df.to_dict(orient="records")
    }
    json_bytes = json.dumps(backup_json, indent=4, ensure_ascii=False).encode("utf-8")

    csv_bundle = {
        f"equipe_{timestamp}.csv": equipe_df.to_csv(index=False).encode("utf-8"),
        f"saisons_{timestamp}.csv": saisons_df.to_csv(index=False).encode("utf-8"),
        f"projets_{timestamp}.csv": projets_df.to_csv(index=False).encode("utf-8"),
        f"taches_{timestamp}.csv": taches_df.to_csv(index=False).encode("utf-8"),
        f"budget_lignes_{timestamp}.csv": budget_df.to_csv(index=False).encode("utf-8"),
    }

    excel_io = BytesIO()
    with pd.ExcelWriter(excel_io, engine="openpyxl") as writer:
        equipe_df.to_excel(writer, index=False, sheet_name="Equipe")
        saisons_df.to_excel(writer, index=False, sheet_name="Saisons")
        projets_df.to_excel(writer, index=False, sheet_name="Projets")
        taches_df.to_excel(writer, index=False, sheet_name="Taches")
        budget_df.to_excel(writer, index=False, sheet_name="Budget")
    excel_bytes = excel_io.getvalue()

    db_bytes = DB_PATH.read_bytes() if DB_PATH.exists() else b""

    # Sauvegarde serveur
    json_file = BACKUP_DIR / f"backup_{timestamp}.json"
    with open(json_file, "wb") as f:
        f.write(json_bytes)

    db_file = BACKUP_DIR / f"database_backup_{timestamp}.db"
    if DB_PATH.exists():
        shutil.copy(DB_PATH, db_file)

    for filename, content in csv_bundle.items():
        with open(EXPORT_DIR / filename, "wb") as f:
            f.write(content)

    with open(EXPORT_DIR / f"export_complet_{timestamp}.xlsx", "wb") as f:
        f.write(excel_bytes)

    return {
        "timestamp": timestamp,
        "json_bytes": json_bytes,
        "csv_bundle": csv_bundle,
        "excel_bytes": excel_bytes,
        "db_bytes": db_bytes,
        "json_filename": f"backup_{timestamp}.json",
        "excel_filename": f"export_complet_{timestamp}.xlsx",
        "db_filename": f"database_backup_{timestamp}.db"
    }

def auto_backup():
    st.session_state["latest_backup"] = generate_backup_files()

def latest_backup():
    if "latest_backup" not in st.session_state:
        st.session_state["latest_backup"] = generate_backup_files()
    return st.session_state["latest_backup"]

# =========================================================
# INITIALISATION
# =========================================================
init_db()
recalculer_finances_projets()

CATEGORIES_SAISON = [
    "CDC", "Compétitif", "PLSJQ", "LDP", "Senior",
    "Féminin", "Camp", "Événement"
]

CATEGORIES_PROJET = [
    "Technique", "Compétitif", "CDC", "Camps", "Formation",
    "Administration", "Événements", "Voyages", "Finance", "Communication"
]

STATUTS_SAISON = ["Préparation", "Actif", "Terminé"]
STATUTS_PROJET = ["Idée", "En préparation", "En attente", "En cours", "Terminé", "Annulé"]
STATUTS_TACHE = ["À faire", "En cours", "Bloqué", "Terminé"]
PRIORITES = ["Haute", "Moyenne", "Basse"]

CATEGORIES_DEPENSE = [
    "Terrain", "Entraîneur", "Staff", "Matériel", "Transport",
    "Hôtel", "Repas", "Communication", "Marketing", "Arbitrage",
    "Administration", "Divers"
]

CATEGORIES_REVENU = [
    "Inscriptions", "Subvention", "Sponsoring", "Partenariat",
    "Vente équipement", "Billetterie", "Autre revenu"
]

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("⚽ Brossard Manager")
menu = st.sidebar.radio(
    "Navigation",
    [
        "Tableau de bord",
        "Saison",
        "Équipe",
        "Projets",
        "Tâches",
        "Calendrier",
        "Chronologie",
        "Budget",
        "Rapports",
        "Sauvegardes"
    ]
)

equipe_df, saisons_df, projets_df, taches_df, budget_lignes_df = charger_donnees()

# =========================================================
# TABLEAU DE BORD
# =========================================================
if menu == "Tableau de bord":
    st.title("Tableau de bord")

    total_saisons = len(saisons_df)
    total_projets = len(projets_df)
    total_taches = len(taches_df)
    total_equipe = len(equipe_df)

    dep_prevu = projets_df["budget_prevu"].sum() if not projets_df.empty else 0
    dep_reel = projets_df["budget_reel"].sum() if not projets_df.empty else 0
    rev_prevu = projets_df["revenu_prevu"].sum() if not projets_df.empty else 0
    rev_reel = projets_df["revenu_reel"].sum() if not projets_df.empty else 0

    resultat_prevu = rev_prevu - dep_prevu
    resultat_reel = rev_reel - dep_reel

    taches_en_retard = 0
    if not taches_df.empty:
        work = taches_df.copy()
        work["date_limite_dt"] = pd.to_datetime(work["date_limite"], errors="coerce")
        today = pd.Timestamp(date.today())
        taches_en_retard = len(work[(work["date_limite_dt"] < today) & (work["statut"] != "Terminé")])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saisons", total_saisons)
    c2.metric("Projets", total_projets)
    c3.metric("Tâches", total_taches)
    c4.metric("Équipe", total_equipe)

    c5, c6, c7 = st.columns(3)
    c5.metric("Dépenses prévues", f"{dep_prevu:,.2f} $")
    c6.metric("Revenus prévus", f"{rev_prevu:,.2f} $")
    c7.metric("Résultat prévu", f"{resultat_prevu:,.2f} $")

    c8, c9, c10 = st.columns(3)
    c8.metric("Dépenses réelles", f"{dep_reel:,.2f} $")
    c9.metric("Revenus réels", f"{rev_reel:,.2f} $")
    c10.metric("Résultat réel", f"{resultat_reel:,.2f} $")

    st.metric("Tâches en retard", taches_en_retard)

    st.markdown("### Résumé des projets")
    if not projets_df.empty:
        show_df = projets_df.copy()
        show_df["résultat_prévu"] = show_df["revenu_prevu"] - show_df["budget_prevu"]
        show_df["résultat_réel"] = show_df["revenu_reel"] - show_df["budget_reel"]
        st.dataframe(
            show_df[[
                "nom", "saison_nom", "categorie", "responsable", "statut",
                "budget_prevu", "revenu_prevu", "résultat_prévu",
                "budget_reel", "revenu_reel", "résultat_réel"
            ]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aucun projet enregistré.")

# =========================================================
# SAISON
# =========================================================
elif menu == "Saison":
    st.title("Gestion des saisons")

    noms_equipe = equipe_df["nom"].tolist() if not equipe_df.empty else []

    with st.form("form_saison"):
        st.subheader("Créer une saison / programme")

        col1, col2, col3 = st.columns(3)
        nom = col1.text_input("Nom de la saison")
        categorie = col2.selectbox("Catégorie", CATEGORIES_SAISON)
        responsable = col3.selectbox("Responsable", noms_equipe if noms_equipe else [""])

        col4, col5 = st.columns(2)
        date_debut = col4.date_input("Date début")
        date_fin = col5.date_input("Date fin")

        statut = st.selectbox("Statut", STATUTS_SAISON)
        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Créer saison")

        if submitted and nom:
            run_query("""
                INSERT INTO saisons
                (nom, categorie, responsable, date_debut, date_fin, statut, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nom,
                categorie,
                responsable,
                str(date_debut),
                str(date_fin),
                statut,
                notes
            ))
            auto_backup()
            st.success("Saison créée avec succès.")
            st.rerun()

    st.subheader("Liste des saisons")
    if not saisons_df.empty:
        st.dataframe(saisons_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune saison enregistrée.")

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
            auto_backup()
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
    saisons_options = {row["nom"]: row["id"] for _, row in saisons_df.iterrows()} if not saisons_df.empty else {}

    with st.form("form_projet"):
        st.subheader("Créer un projet")
        c1, c2, c3 = st.columns(3)

        nom = c1.text_input("Nom du projet")
        saison_nom = c2.selectbox("Saison", list(saisons_options.keys()) if saisons_options else [""])
        categorie = c3.selectbox("Catégorie", CATEGORIES_PROJET)

        c4, c5, c6 = st.columns(3)
        responsable = c4.selectbox("Responsable", noms_equipe if noms_equipe else [""])
        statut = c5.selectbox("Statut", STATUTS_PROJET)
        priorite = c6.selectbox("Priorité", PRIORITES)

        c7, c8 = st.columns(2)
        date_debut = c7.date_input("Date de début", value=date.today())
        date_fin = c8.date_input("Date de fin", value=date.today() + timedelta(days=30))

        description = st.text_area("Description")
        submitted = st.form_submit_button("Créer le projet")

        if submitted and nom:
            saison_id = saisons_options[saison_nom] if saison_nom in saisons_options else None
            run_query("""
                INSERT INTO projets
                (nom, saison_id, categorie, responsable, statut, priorite, date_debut, date_fin,
                 budget_prevu, budget_reel, revenu_prevu, revenu_reel, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nom, saison_id, categorie, responsable, statut, priorite,
                str(date_debut), str(date_fin),
                0, 0, 0, 0, description
            ))
            auto_backup()
            st.success("Projet créé avec succès.")
            st.rerun()

    st.subheader("Liste des projets")
    if not projets_df.empty:
        show_df = projets_df.copy()
        show_df["résultat_prévu"] = show_df["revenu_prevu"] - show_df["budget_prevu"]
        show_df["résultat_réel"] = show_df["revenu_reel"] - show_df["budget_reel"]
        st.dataframe(show_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun projet enregistré.")

# =========================================================
# TÂCHES
# =========================================================
elif menu == "Tâches":
    st.title("Tâches")

    projets_options = {row["nom"]: row["id"] for _, row in projets_df.iterrows()} if not projets_df.empty else {}
    noms_equipe = equipe_df["nom"].tolist() if not equipe_df.empty else []

    with st.form("form_tache"):
        st.subheader("Ajouter une tâche")
        c1, c2, c3 = st.columns(3)

        projet_nom = c1.selectbox("Projet", list(projets_options.keys()) if projets_options else [""])
        titre = c2.text_input("Titre de la tâche")
        responsable = c3.selectbox("Responsable", noms_equipe if noms_equipe else [""])

        c4, c5, c6 = st.columns(3)
        statut = c4.selectbox("Statut", STATUTS_TACHE)
        priorite = c5.selectbox("Priorité", PRIORITES)
        date_debut = c6.date_input("Date de début", value=date.today(), key="date_debut_tache")

        c7, c8, c9 = st.columns(3)
        date_limite = c7.date_input("Date limite", value=date.today() + timedelta(days=7), key="date_limite_tache")
        cout_prevu = c8.number_input("Coût prévu", min_value=0.0, step=10.0)
        cout_reel = c9.number_input("Coût réel", min_value=0.0, step=10.0)

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
            auto_backup()
            st.success("Tâche ajoutée avec succès.")
            st.rerun()

    st.subheader("Liste des tâches")
    if not taches_df.empty:
        st.dataframe(taches_df, use_container_width=True, hide_index=True)
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

        vue = st.radio("Vue", ["Agenda", "Semaine"], horizontal=True)

        if vue == "Agenda":
            agenda = cal_df.sort_values("date_limite_dt")
            agenda["date_limite_aff"] = agenda["date_limite_dt"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                agenda[["date_limite_aff", "projet", "titre", "responsable", "statut", "priorite"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            ref = st.date_input("Semaine de référence", value=date.today())
            ref = pd.Timestamp(ref)
            fin = ref + pd.Timedelta(days=6)
            semaine = cal_df[(cal_df["date_limite_dt"] >= ref) & (cal_df["date_limite_dt"] <= fin)].copy()

            if semaine.empty:
                st.info("Aucune tâche prévue pour cette semaine.")
            else:
                semaine["jour"] = semaine["date_limite_dt"].dt.strftime("%A %d/%m")
                semaine["détail"] = semaine["titre"] + " | " + semaine["responsable"].fillna("") + " | " + semaine["statut"].fillna("")
                pivot = semaine.groupby("jour")["détail"].apply(lambda x: " ; ".join(x)).reset_index()
                st.dataframe(pivot, use_container_width=True, hide_index=True)

# =========================================================
# CHRONOLOGIE
# =========================================================
elif menu == "Chronologie":
    st.title("Chronologie")

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
                    hover_data=["saison_nom", "categorie", "responsable", "priorite", "budget_prevu", "revenu_prevu"]
                )
                fig.update_yaxes(autorange="reversed")
                fig.update_layout(height=650)
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
    st.title("Budget détaillé")

    projets_options = {row["nom"]: row["id"] for _, row in projets_df.iterrows()} if not projets_df.empty else {}

    if not projets_options:
        st.info("Créez d'abord un projet.")
    else:
        st.subheader("Ajouter une ligne financière")
        with st.form("form_budget_ligne"):
            c1, c2, c3 = st.columns(3)
            projet_nom = c1.selectbox("Projet", list(projets_options.keys()))
            type_ligne = c2.selectbox("Type", ["Dépense", "Revenu"])
            categorie = c3.selectbox("Catégorie", CATEGORIES_DEPENSE if type_ligne == "Dépense" else CATEGORIES_REVENU)

            c4, c5, c6 = st.columns(3)
            description = c4.text_input("Description")
            quantite = c5.number_input("Quantité", min_value=1.0, step=1.0, value=1.0)
            montant_unitaire_prevu = c6.number_input("Montant unitaire prévu", min_value=0.0, step=1.0)

            c7, c8 = st.columns(2)
            montant_unitaire_reel = c7.number_input("Montant unitaire réel", min_value=0.0, step=1.0)
            notes = c8.text_input("Notes")

            submitted = st.form_submit_button("Ajouter la ligne")

            if submitted:
                projet_id = projets_options[projet_nom]
                total_prevu = quantite * montant_unitaire_prevu
                total_reel = quantite * montant_unitaire_reel

                run_query("""
                    INSERT INTO budget_lignes
                    (projet_id, type_ligne, categorie, description, quantite, montant_unitaire_prevu, montant_unitaire_reel, total_prevu, total_reel, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    projet_id, type_ligne, categorie, description, quantite,
                    montant_unitaire_prevu, montant_unitaire_reel,
                    total_prevu, total_reel, notes
                ))
                recalculer_finances_projets()
                auto_backup()
                st.success("Ligne financière ajoutée avec succès.")
                st.rerun()

        st.markdown("### Projet")
        projet_filtre = st.selectbox("Voir le budget de", list(projets_options.keys()))
        budget_projet = budget_lignes_df[budget_lignes_df["projet"] == projet_filtre].copy()

        if budget_projet.empty:
            st.info("Aucune ligne financière pour ce projet.")
        else:
            budget_projet["écart"] = budget_projet["total_prevu"] - budget_projet["total_reel"]

            st.dataframe(
                budget_projet[[
                    "type_ligne", "categorie", "description", "quantite",
                    "montant_unitaire_prevu", "montant_unitaire_reel",
                    "total_prevu", "total_reel", "écart", "notes"
                ]],
                use_container_width=True,
                hide_index=True
            )

            dep_df = budget_projet[budget_projet["type_ligne"] == "Dépense"]
            rev_df = budget_projet[budget_projet["type_ligne"] == "Revenu"]

            dep_prevu = dep_df["total_prevu"].sum() if not dep_df.empty else 0
            dep_reel = dep_df["total_reel"].sum() if not dep_df.empty else 0
            rev_prevu = rev_df["total_prevu"].sum() if not rev_df.empty else 0
            rev_reel = rev_df["total_reel"].sum() if not rev_df.empty else 0

            resultat_prevu = rev_prevu - dep_prevu
            resultat_reel = rev_reel - dep_reel

            c1, c2, c3 = st.columns(3)
            c1.metric("Dépenses prévues", f"{dep_prevu:,.2f} $")
            c2.metric("Revenus prévus", f"{rev_prevu:,.2f} $")
            c3.metric("Résultat prévu", f"{resultat_prevu:,.2f} $")

            c4, c5, c6 = st.columns(3)
            c4.metric("Dépenses réelles", f"{dep_reel:,.2f} $")
            c5.metric("Revenus réels", f"{rev_reel:,.2f} $")
            c6.metric("Résultat réel", f"{resultat_reel:,.2f} $")

            resume_cat = budget_projet.groupby(["type_ligne", "categorie"], as_index=False)[["total_prevu", "total_reel"]].sum()
            fig = px.bar(
                resume_cat,
                x="categorie",
                y=["total_prevu", "total_reel"],
                color="type_ligne",
                barmode="group",
                title=f"Finances par catégorie - {projet_filtre}"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Résumé global")
        if not projets_df.empty:
            global_df = projets_df.copy()
            global_df["résultat_prévu"] = global_df["revenu_prevu"] - global_df["budget_prevu"]
            global_df["résultat_réel"] = global_df["revenu_reel"] - global_df["budget_reel"]
            st.dataframe(
                global_df[[
                    "nom", "saison_nom", "categorie", "responsable",
                    "budget_prevu", "revenu_prevu", "résultat_prévu",
                    "budget_reel", "revenu_reel", "résultat_réel", "statut"
                ]],
                use_container_width=True,
                hide_index=True
            )

# =========================================================
# RAPPORTS
# =========================================================
elif menu == "Rapports":
    st.title("Rapports")

    if projets_df.empty:
        st.info("Aucun projet enregistré.")
    else:
        rapport_df = projets_df.copy()
        rapport_df["résultat_prévu"] = rapport_df["revenu_prevu"] - rapport_df["budget_prevu"]
        rapport_df["résultat_réel"] = rapport_df["revenu_reel"] - rapport_df["budget_reel"]

        filtre_saison = st.selectbox(
            "Filtrer par saison",
            ["Toutes"] + sorted([x for x in rapport_df["saison_nom"].dropna().unique().tolist()])
        )

        filtre_statut = st.selectbox(
            "Filtrer par statut",
            ["Tous"] + STATUTS_PROJET
        )

        if filtre_saison != "Toutes":
            rapport_df = rapport_df[rapport_df["saison_nom"] == filtre_saison]
        if filtre_statut != "Tous":
            rapport_df = rapport_df[rapport_df["statut"] == filtre_statut]

        st.dataframe(
            rapport_df[[
                "nom", "saison_nom", "categorie", "responsable", "statut",
                "budget_prevu", "revenu_prevu", "résultat_prévu",
                "budget_reel", "revenu_reel", "résultat_réel"
            ]],
            use_container_width=True,
            hide_index=True
        )

# =========================================================
# SAUVEGARDES
# =========================================================
elif menu == "Sauvegardes":
    st.title("Sauvegardes et exportation")

    if st.button("Créer une sauvegarde maintenant"):
        st.session_state["latest_backup"] = generate_backup_files()
        st.success("Sauvegarde créée avec succès.")

    backup = latest_backup()

    st.markdown("### Dernière sauvegarde")
    st.write(f"Horodatage : {backup['timestamp']}")

    st.markdown("### Télécharger les sauvegardes")
    st.download_button(
        "Télécharger backup JSON",
        data=backup["json_bytes"],
        file_name=backup["json_filename"],
        mime="application/json"
    )

    st.download_button(
        "Télécharger la base SQLite",
        data=backup["db_bytes"],
        file_name=backup["db_filename"],
        mime="application/octet-stream"
    )

    st.download_button(
        "Télécharger export Excel",
        data=backup["excel_bytes"],
        file_name=backup["excel_filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("### Télécharger les CSV")
    for filename, content in backup["csv_bundle"].items():
        st.download_button(
            f"Télécharger {filename}",
            data=content,
            file_name=filename,
            mime="text/csv",
            key=filename
        )

    st.markdown("### Historique serveur")
    backup_files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    export_files = sorted(os.listdir(EXPORT_DIR), reverse=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Fichiers de sauvegarde")
        if backup_files:
            for f in backup_files[:20]:
                st.write(f)
        else:
            st.info("Aucune sauvegarde disponible.")

    with col_b:
        st.subheader("Fichiers exportés")
        if export_files:
            for f in export_files[:20]:
                st.write(f)
        else:
            st.info("Aucune exportation disponible.")
