CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.raw_salaries (
    id_salarie INTEGER,
    nom VARCHAR,
    prenom VARCHAR,
    date_naissance DATE,
    date_embauche DATE,
    business_unit VARCHAR,
    type_contrat VARCHAR,
    salaire_brut_annuel DOUBLE,
    adresse_domicile VARCHAR,
    mode_transport_declare VARCHAR,
    date_ingestion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.raw_sports (
    id_sport INTEGER,
    libelle VARCHAR,
    categorie VARCHAR,
    date_ingestion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.raw_pratiques_sportives (
    id_salarie INTEGER,
    id_sport INTEGER,
    date_ingestion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.raw_activites_sportives (
    id_activite INTEGER,
    id_salarie INTEGER,
    id_sport INTEGER,
    date_debut TIMESTAMP,
    date_fin TIMESTAMP,
    distance_m INTEGER,
    duree_secondes INTEGER,
    commentaire VARCHAR,
    source VARCHAR,
    date_ingestion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.raw_parametres_regles (
    id_parametre INTEGER,
    version_parametre VARCHAR,
    taux_prime DOUBLE,
    seuil_activites_wellness INTEGER,
    max_km_marche DOUBLE,
    max_km_velo DOUBLE,
    date_debut_validite DATE,
    date_fin_validite DATE,
    cree_par VARCHAR,
    date_ingestion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.audit_log (
    id_log INTEGER,
    nom_pipeline VARCHAR,
    statut VARCHAR,
    message VARCHAR,
    date_execution TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);