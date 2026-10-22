# Protein/ligand preparation layer on top of the engine.
# PDB2PQR/PROPKA/RDKit live in their own Python 3.12 env named "prep".
FROM activesite-engine:at26
RUN micromamba create -y -n prep -c conda-forge python=3.12 rdkit=2026.03.1 pdb2pqr=3.6.1 propka=3.5.1 && micromamba clean -a -y
