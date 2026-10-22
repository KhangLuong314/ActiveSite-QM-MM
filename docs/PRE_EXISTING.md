# Pre-existing components and data

Everything below existed before the build window (2026-10-22 00:00 UTC) or is third-party. Everything else in the
repository was written during the window; see `docs/prompts/PROMPT_LOG.md`.

| path | origin | date | used by |
|---|---|---|---|
| `data/reference/qmmm_dft/step3_pbcsetup.parm7` | lab reference topology for solvated I-PpoI/DNA (AmberTools, CHARMM-GUI-style setup) | before 2026-10-22 | `MolSystem`, QM-region proposal, sander engine, tests |
| `data/reference/qmmm_dft/prod00.ncrst` | lab production-frame coordinates for the same system | before 2026-10-22 | same |
| `data/reference/qmmm_dft/qmhub.ini`, `legacy/qmhub.ini` | lab QMHub configuration (B3LYP/6-31G* high level, PM6/PM3 low level) | before 2026-10-22 | expert theory level cited in cards; seed script |
| `data/reference/qmmm_dft/step5.00_equilibration.mdin`, `step6.00_equilibration.mdin`, `legacy/step5.00_equilibration.mdin` | lab sander QM/MM input templates | before 2026-10-22 | documentation only (the engine writes its own single-point mdin) |
| `data/reference/qmmm_dft/gen_inputs.sh`, `gen_qmmask.py`, `gen_cvs.py`, `gen_cv.sh`, `cv.rst` | lab umbrella-sampling setup scripts; `gen_inputs.sh` defines the expert QM mask and qmcharge for site A, `gen_qmmask.py` lists site-B residues | before 2026-10-22 | tests (expert comparison), `seed/seed.py` |
| `data/reference/abl/2hyy.pdb` | RCSB PDB entry 2HYY (ABL kinase + imatinib) | deposited 2006; downloaded before 2026-10-22 | ligand case preparation, tests |
| `data/reference/abl/abl_ligand.yaml`, `abl_ligand_model_0.cif` | lab ligand notes / model for ABL-imatinib | before 2026-10-22 | not used by code |
| `data/reference/egfr/1m17.pdb` | RCSB PDB entry 1M17 (EGFR kinase + erlotinib) | deposited 2002; downloaded before 2026-10-22 | ligand case preparation, tests |
| `data/reference/eda/barrier_res_table.pkl` | lab energy-decomposition pickle | before 2026-10-22 | not loaded by any code (pickles are never unpickled here) |
| `data/reference/fmatch/energy.npy`, `mm_charge.npy`, `list.dft_forces`, `list.model` | lab force-matching arrays and lists | before 2026-10-22 | not used by code |
| `data/reference/wtp/theories.csv` | list of theory levels (tag, method, basis) | before 2026-10-22 | documentation; `seed/seed.py` notes it is not an EDA table |
| `cases/*.json` | benchmark case definitions (questions, PDB ids, SMILES from RCSB chemcomp, literature contacts) | 2026-10-21 (scaffold) | all runs |
| Docker base images | `mambaorg/micromamba:1.5.10`; conda-forge `ambertools=26.0`, `xtb=6.7.1`, `rdkit=2026.03.1`, `pdb2pqr=3.6.1`, `propka=3.5.1`; `postgres:16-alpine`; `bitnamilegacy/minio:2025.4.22` | third-party | `docker/*.Dockerfile`, `docker-compose.yml` |
| Pre-window scaffold (2026-10-21) | first-pass modules (`partitioning.py`, `protonation.py`, `chimerax.py`, `critic.py`, `planner.py`, `explainer.py`, `scout.py`) written the day before the window; the fabricated energies, seeded memories and radius pipeline they shipped with were removed in P0/P7 | 2026-10-21 | partly still imported by older tests; not on the judged path |
| Chemistry spike benchmark | none of its files are included | — | — |

Large binary files (`*.parm7`, `*.ncrst`, `fmatch/*.npy`, `eda/*.pkl`) are listed with SHA-256 in
`data/reference/LARGE_FILES.sha256`; `scripts/fetch_reference.sh` restores them from `REFERENCE_URL` or
`REFERENCE_PATH` and verifies the hashes.
