CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.salaries (
    id_salarie INTEGER PRIMARY KEY,
    nom VARCHAR,
    prenom VARCHAR,
    date_naissance DATE,
    date_embauche DATE,
    business_unit VARCHAR,
    type_contrat VARCHAR,
    salaire_brut_annuel DOUBLE,
    adresse_domicile VARCHAR,
    mode_transport_declare VARCHAR,
    mode_transport_normalise VARCHAR,
    distance_domicile_km DOUBLE,
    transport_eligible BOOLEAN
);

CREATE TABLE IF NOT EXISTS silver.sports (
    id_sport INTEGER PRIMARY KEY,
    libelle VARCHAR,
    categorie VARCHAR
);

CREATE TABLE IF NOT EXISTS silver.pratiques_sportives (
    id_salarie INTEGER,
    id_sport INTEGER
);

CREATE TABLE IF NOT EXISTS silver.activites_sportives (
    id_activite INTEGER PRIMARY KEY,
    id_salarie INTEGER,
    id_sport INTEGER,
    date_debut TIMESTAMP,
    date_fin TIMESTAMP,
    distance_m INTEGER,
    duree_secondes INTEGER,
    commentaire VARCHAR,
    source VARCHAR,
    activite_valide BOOLEAN
);

CREATE TABLE IF NOT EXISTS silver.parametres_regles (
    id_parametre INTEGER PRIMARY KEY,
    version_parametre VARCHAR,
    taux_prime DOUBLE,
    seuil_activites_wellness INTEGER,
    max_km_marche DOUBLE,
    max_km_velo DOUBLE,
    date_debut_validite DATE,
    date_fin_validite DATE,
    cree_par VARCHAR
);

CREATE TABLE IF NOT EXISTS silver.quarantaine_activites (
    id_activite INTEGER,
    id_salarie INTEGER,
    raison_rejet VARCHAR,
    date_rejet TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);