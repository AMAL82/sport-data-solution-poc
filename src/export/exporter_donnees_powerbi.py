"""
Export des tables Gold vers PowerBI.

Rôle :
- exporter les tables Gold en CSV et Parquet ;
- alimenter le dossier data/exports ;
- faciliter l'import dans PowerBI.

Exemple :
    python src/export/exporter_donnees_powerbi.py
"""

from pathlib import Path
from datetime import datetime
import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"
DOSSIER_EXPORTS = RACINE_PROJET / "data" / "exports"


TABLES_A_EXPORTER = [
    "gold.avantages",
    "gold.avantages_calcules",
    "gold.anomalies",
    "gold.messages_slack",
    "gold.kpi_financiers",
    "gold.kpi_pratiques_sportives",
    "gold.kpi_anomalies",
]


def verifier_base() -> None:
    """
    Vérifie que la base DuckDB existe.
    """
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(f"Base DuckDB introuvable : {CHEMIN_BASE}")


def preparer_dossier_exports() -> None:
    """
    Crée le dossier d'exports si nécessaire.
    """
    DOSSIER_EXPORTS.mkdir(parents=True, exist_ok=True)


def nom_fichier_export(table: str) -> str:
    """
    Transforme un nom de table en nom de fichier.
    Exemple : gold.kpi_financiers -> kpi_financiers
    """
    return table.split(".")[-1]


def exporter_table(
    connexion: duckdb.DuckDBPyConnection,
    table: str,
) -> tuple[int, Path, Path]:
    """
    Exporte une table en CSV et Parquet.
    """
    nom = nom_fichier_export(table)

    chemin_csv = DOSSIER_EXPORTS / f"{nom}.csv"
    chemin_parquet = DOSSIER_EXPORTS / f"{nom}.parquet"

    nb_lignes = connexion.execute(
        f"SELECT COUNT(*) FROM {table};"
    ).fetchone()[0]

    chemin_csv_sql = str(chemin_csv).replace("\\", "/").replace("'", "''")
    chemin_parquet_sql = str(chemin_parquet).replace("\\", "/").replace("'", "''")

    connexion.execute(
        f"""
        COPY {table}
        TO '{chemin_csv_sql}'
        (HEADER, DELIMITER ',');
        """
    )

    connexion.execute(
        f"""
        COPY {table}
        TO '{chemin_parquet_sql}'
        (FORMAT PARQUET);
        """
    )

    return nb_lignes, chemin_csv, chemin_parquet

    connexion.execute(
        f"""
        COPY {table}
        TO '{chemin_parquet.as_posix()}'
        (FORMAT PARQUET);
        """
    )

    return nb_lignes, chemin_csv, chemin_parquet


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
            message,
            date_execution
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        [
            prochain_id,
            "export_powerbi",
            statut,
            message,
            datetime.now(),
        ],
    )


def exporter_donnees_powerbi() -> None:
    """
    Exécute l'export complet des tables Gold.
    """
    verifier_base()
    preparer_dossier_exports()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        print("Export des tables Gold vers PowerBI...\n")

        total_lignes = 0

        for table in TABLES_A_EXPORTER:
            nb_lignes, chemin_csv, chemin_parquet = exporter_table(connexion, table)
            total_lignes += nb_lignes

            print(f"{table}")
            print(f"  - lignes : {nb_lignes}")
            print(f"  - CSV : {chemin_csv}")
            print(f"  - Parquet : {chemin_parquet}")

        message = (
            f"{len(TABLES_A_EXPORTER)} tables exportées, "
            f"{total_lignes} lignes au total"
        )

        ajouter_log_audit(connexion, "SUCCES", message)

        print("\nExport terminé avec succès.")
        print(message)
        print(f"Dossier exports : {DOSSIER_EXPORTS}")

    finally:
        connexion.close()


if __name__ == "__main__":
    exporter_donnees_powerbi()