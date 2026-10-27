-- Registers the DataScout tables in a local Zetaris platform (see scripts/zetaris/load.sh).
-- expert_runs = the lab expert's QM regions; eda_synthetic is a SYNTHETIC placeholder; rcsb_entries = cached RCSB search.
CREATE LIGHTNING DATABASE ACTIVESITE DESCRIBE BY "ActiveSite QM-MM DataScout tables, lab expert runs, SYNTHETIC EDA placeholder, RCSB entries" OPTIONS ();
CREATE LIGHTNING FILESTORE TABLE expert_runs FROM ACTIVESITE
FORMAT csv
OPTIONS (
  path "file:///home/zetaris/customer-data/shared/activesite/lab_runs",
  header "true",
  inferSchema "true"
);
CREATE LIGHTNING FILESTORE TABLE eda_synthetic FROM ACTIVESITE
FORMAT csv
OPTIONS (
  path "file:///home/zetaris/customer-data/shared/activesite/eda_synthetic",
  header "true",
  inferSchema "true"
);
CREATE LIGHTNING FILESTORE TABLE rcsb_entries FROM ACTIVESITE
FORMAT csv
OPTIONS (
  path "file:///home/zetaris/customer-data/shared/activesite/rcsb_entries",
  header "true",
  inferSchema "true"
);
