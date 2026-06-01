"""
Ingestion des données RH vers DuckDB.

Rôle du script :
- lire le fichier Excel RH ;
- normaliser les noms de colonnes ;
- charger les salariés dans bronze.raw_salaries ;
- vérifier le nombre de lignes chargées.

Exemple :
    python src/ingestion/ingerer_donnees_rh.py

Pré-requis :
    python src/utils/initialiser_entrepot.py
"""

from pathlib import Path
import argparse

import duckdb
import pandas as pd


RACINE_PROJET = Path(__file__).resolve().parents[2]

CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"
CHEMIN_FICHIER_RH = RACINE_PROJET / "data" / "input" / "Donnees_RH.xlsx"


COLONNES_ATTENDUES = {
    "ID salarié": "id_salarie",
    "Nom": "nom",
    "Prénom": "prenom",
    "Date de naissance": "date_naissance",
    "Date d'embauche": "date_embauche",
    "BU": "business_unit",
    "Type de contrat": "type_contrat",
    "Salaire brut": "salaire_brut_annuel",
    "Adresse du domicile": "adresse_domicile",
    "Moyen de déplacement": "mode_transport_declare",
}


def verifier_fichier_existe(chemin_fichier: Path) -> None:
    """
    Vérifie que le fichier Excel RH existe.
    """
    if not chemin_fichier.exists():
        raise FileNotFoundError(
            f"Fichier RH introuvable : {chemin_fichier}\n"
            "Place le fichier Excel dans data/input/ et renomme-le Donnees_RH.xlsx"
        )


def lire_fichier_rh(chemin_fichier: Path) -> pd.DataFrame:
    """
    Lit le fichier Excel RH.
    """
    df = pd.read_excel(chemin_fichier)

    colonnes_manquantes = [
        colonne for colonne in COLONNES_ATTENDUES if colonne not in df.columns
    ]

    if colonnes_manquantes:
        raise ValueError(
            "Colonnes manquantes dans le fichier RH : "
            + ", ".join(colonnes_manquantes)
        )

    df = df[list(COLONNES_ATTENDUES.keys())].rename(columns=COLONNES_ATTENDUES)

    df["date_naissance"] = pd.to_datetime(df["date_naissance"], errors="coerce").dt.date
    df["date_embauche"] = pd.to_datetime(df["date_embauche"], errors="coerce").dt.date

    df["id_salarie"] = df["id_salarie"].astype("Int64")
    df["salaire_brut_annuel"] = pd.to_numeric(
        df["salaire_brut_annuel"], errors="coerce"
    )

    colonnes_texte = [
        "nom",
        "prenom",
        "business_unit",
        "type_contrat",
        "adresse_domicile",
        "mode_transport_declare",
    ]

    for colonne in colonnes_texte:
        df[colonne] = df[colonne].astype(str).str.strip()

    return df


def vider_table_bronze(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Vide la table bronze.raw_salaries avant rechargement.
    """
    connexion.execute("DELETE FROM bronze.raw_salaries;")


def charger_dans_bronze(
    connexion: duckdb.DuckDBPyConnection,
    df_salaries: pd.DataFrame,
) -> None:
    """
    Charge le DataFrame RH dans bronze.raw_salaries.
    """
    connexion.register("df_salaries", df_salaries)

    connexion.execute(
        """
        INSERT INTO bronze.raw_salaries (
            id_salarie,
            nom,
            prenom,
            date_naissance,
            date_embauche,
            business_unit,
            type_contrat,
            salaire_brut_annuel,
            adresse_domicile,
            mode_transport_declare
        )
        SELECT
            id_salarie,
            nom,
            prenom,
            date_naissance,
            date_embauche,
            business_unit,
            type_contrat,
            salaire_brut_annuel,
            adresse_domicile,
            mode_transport_declare
        FROM df_salaries;
        """
    )

    connexion.unregister("df_salaries")


def compter_lignes_bronze(connexion: duckdb.DuckDBPyConnection) -> int:
    """
    Compte le nombre de salariés chargés.
    """
    resultat = connexion.execute(
        "SELECT COUNT(*) FROM bronze.raw_salaries;"
    ).fetchone()

    return resultat[0]


def ajouter_log_audit(
    connexion: duckdb.DuckDBPyConnection,
    statut: str,
    message: str,
) -> None:
    """
    Ajoute une ligne dans bronze.audit_log.
    """
    prochain_id = connexion.execute(
        "SELECT COALESCE(MAX(id_log), 0) + 1 FROM bronze.audit_log;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO bronze.audit_log (
            id_log,
            nom_pipeline,
            statut,
            message
        )
        VALUES (?, ?, ?, ?);
        """,
        [
            prochain_id,
            "ingestion_donnees_rh",
            statut,
            message,
        ],
    )


def ingerer_donnees_rh(chemin_fichier: Path = CHEMIN_FICHIER_RH) -> None:
    """
    Exécute l'ingestion complète des données RH.
    """
    verifier_fichier_existe(chemin_fichier)

    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}\n"
            "Lance d'abord : python src/utils/initialiser_entrepot.py"
        )

    df_salaries = lire_fichier_rh(chemin_fichier)

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        vider_table_bronze(connexion)
        charger_dans_bronze(connexion, df_salaries)

        nb_lignes = compter_lignes_bronze(connexion)

        message = f"{nb_lignes} salariés chargés dans bronze.raw_salaries"
        ajouter_log_audit(connexion, "SUCCES", message)

        print("Ingestion RH terminée avec succès.")
        print(f"Fichier source : {chemin_fichier}")
        print(f"Lignes lues : {len(df_salaries)}")
        print(f"Lignes chargées dans DuckDB : {nb_lignes}")

    except Exception as erreur:
        ajouter_log_audit(connexion, "ECHEC", str(erreur))
        raise

    finally:
        connexion.close()


def parser_arguments() -> argparse.Namespace:
    """
    Parse les arguments de ligne de commande.
    """
    parser = argparse.ArgumentParser(
        description="Charge les données RH Excel dans DuckDB."
    )

    parser.add_argument(
        "--fichier",
        type=str,
        default=str(CHEMIN_FICHIER_RH),
        help="Chemin du fichier Excel RH à charger.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    arguments = parser_arguments()
    ingerer_donnees_rh(Path(arguments.fichier))