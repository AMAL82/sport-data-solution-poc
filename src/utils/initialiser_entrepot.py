"""
Initialisation de l'entrepôt DuckDB.

Rôle du script :
- créer le fichier de base DuckDB ;
- exécuter les scripts SQL Bronze, Silver et Gold ;
- permettre une réinitialisation complète avec l'option --force.

Exemples :
    python src/utils/initialiser_entrepot.py
    python src/utils/initialiser_entrepot.py --force
"""

from pathlib import Path
import argparse
import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]

CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"

SCRIPTS_SQL = [
    RACINE_PROJET / "sql" / "bronze" / "creer_tables_bronze.sql",
    RACINE_PROJET / "sql" / "silver" / "creer_tables_silver.sql",
    RACINE_PROJET / "sql" / "gold" / "creer_tables_gold.sql",
]


def supprimer_base_si_force(force: bool) -> None:
    """
    Supprime la base DuckDB existante si l'option --force est utilisée.
    """
    if force and CHEMIN_BASE.exists():
        CHEMIN_BASE.unlink()
        print(f"Base existante supprimée : {CHEMIN_BASE}")


def verifier_scripts_sql() -> None:
    """
    Vérifie que tous les fichiers SQL nécessaires existent.
    """
    fichiers_manquants = [str(script) for script in SCRIPTS_SQL if not script.exists()]

    if fichiers_manquants:
        message = "Scripts SQL manquants :\n" + "\n".join(fichiers_manquants)
        raise FileNotFoundError(message)


def executer_script_sql(connexion: duckdb.DuckDBPyConnection, chemin_script: Path) -> None:
    """
    Exécute un script SQL dans DuckDB.
    """
    contenu_sql = chemin_script.read_text(encoding="utf-8")
    connexion.execute(contenu_sql)
    print(f"Script exécuté : {chemin_script}")


def initialiser_entrepot(force: bool = False) -> None:
    """
    Initialise l'entrepôt DuckDB.
    """
    supprimer_base_si_force(force)
    verifier_scripts_sql()

    CHEMIN_BASE.parent.mkdir(parents=True, exist_ok=True)

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        for script in SCRIPTS_SQL:
            executer_script_sql(connexion, script)

        connexion.execute(
            """
            INSERT INTO bronze.audit_log (id_log, nom_pipeline, statut, message)
            VALUES (
                1,
                'initialisation_entrepot',
                'SUCCES',
                'Entrepôt DuckDB initialisé avec succès'
            );
            """
        )

        print("\nInitialisation terminée avec succès.")
        print(f"Base DuckDB créée ici : {CHEMIN_BASE}")

    finally:
        connexion.close()


def parser_arguments() -> argparse.Namespace:
    """
    Parse les arguments de ligne de commande.
    """
    parser = argparse.ArgumentParser(
        description="Initialise l'entrepôt DuckDB du projet Sport Data Solution."
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Supprime et recrée la base DuckDB si elle existe déjà.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    arguments = parser_arguments()
    initialiser_entrepot(force=arguments.force)