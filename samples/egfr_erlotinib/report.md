# ActiveSite report — `egfr_erlotinib` (run `20261022-190649-7cc564`)

**Question:** Prepare EGFR kinase with erlotinib from the 1M17 crystal structure (downloaded from RCSB) and compute the PM6 QM/MM energy of erlotinib in its pocket. Explain every protonation and setup choice.

**Result:** converged — ESCF -8.286 kcal/mol, total -9861.80 kcal/mol, 0 link atoms, 1.13 s engine time

**Engine:** sander in Docker

**Ligand charge:** +0; chain A (REMARK 465/470 pocket completeness); His overrides 0; memory used: False

## Binding mode
- published contacts recovered: 1/1 MET769 2.90 Å
- missed: []
- expected absent: {'THR766': True}
- extra polar contacts: ['GLY772']

## Decision cards
### 1. residue_inclusion: chain
- **Choice:** chain A (REMARK 465/470 pocket completeness) *(confidence 1.00)*
- **Why:** 77 CA within 12 Å of the ligand; 0 gaps adjacent, 0 residues with missing atoms in the pocket, 21 missing residues in the chain
- **Evidence:** {"source": "REMARK 465/470 of 1m17.pdb"}

### 2. protonation_state: protein protonation
- **Choice:** PDB2PQR + PROPKA at pH 7.4: 9 non-default states, His {'HIS749': 'HID', 'HIS781': 'HID', 'HIS811': 'HIE', 'HIS826': 'HIE', 'HIS846': 'HID', 'HIS864': 'HID', 'HIS869': 'HID', 'HIS964': 'HID'} *(confidence 0.75)*
- **Why:** 112 titratable groups predicted; 2 His within 1.0 pKa of the pH
- **Evidence:** {"gap_warnings": ["WARNING:Gap in backbone detected between HIS A 964 and LEU A 977!"], "source": "pdb2pqr/propka in activesite-prep:at26"}

### 3. protonation_state: ligand
- **Choice:** kept neutral *(confidence 0.80)*
- **Why:** no tertiary amine (N with three C neighbours) has a backbone O within 3.3 Å
- **Evidence:** {"source": "crystal geometry", "rule": "tertiary amine + backbone O < 3.3 \u00c5"}

### 4. theory_selection: ligand force field
- **Choice:** GAFF2 + AM1-BCC, net charge +0 (cached) *(confidence 1.00)*
- **Why:** charge sum +0.0000, residual spread +0.0000 e over 52 atoms
- **Evidence:** {"charge_sum": 0.0, "charge_residual_spread": 2e-06, "ligand_atoms": 52, "cached": true, "cache_key": "1e11abd86f46d63f", "source": "antechamber/parmchk2"}

### 5. link_atom: QM region
- **Choice:** whole ligand (:LIG), no link atoms *(confidence 1.00)*
- **Why:** a closed-shell whole ligand needs no boundary treatment
- **Rejected:**
  - ligand + pocket side chains: covalent cuts add link atoms and PM6 cost; the question is the ligand's energy in its pocket
- **Evidence:** {"mask": ":LIG", "link_atoms": 0, "source": "setup"}

### 6. solvent_handling: solvent
- **Choice:** implicit solvent (igb=5, mbondi2) for the QM/MM single point *(confidence 0.50)*
- **Why:** trade-off: fast and judge-runnable, but bridging waters and bulk screening are approximated
- **Rejected:**
  - explicit TIP3P box + PME: hours of equilibration; crystal waters (incl. the Thr766 bridge) are removed either way
- **Evidence:** {"igb": 5, "cut": 999.0, "source": "design choice"}

### 7. critic_correction: ligand_charge_sum
- **Choice:** passed: |charge sum +0.0000 - formal +0| = 0.00e+00 *(confidence 0.50)*
- **Why:** LigandCritic precheck
- **Evidence:** {"margin": 0.001, "passed": true, "blocking": false, "source": "LigandCritic.precheck"}

### 8. critic_correction: pocket_built
- **Choice:** passed: centroid shift 0.0 Å (limit 1.0), closest protein heavy atom 2.699 Å (limit 4.0) *(confidence 1.00)*
- **Why:** LigandCritic precheck (blocking)
- **Evidence:** {"margin": 1.0, "passed": true, "blocking": true, "source": "LigandCritic.precheck"}

### 9. critic_correction: pocket_min
- **Choice:** passed: centroid shift 0.02 Å (limit 1.0), closest protein heavy atom 2.903 Å (limit 4.0) *(confidence 0.99)*
- **Why:** LigandCritic precheck (blocking)
- **Evidence:** {"margin": 0.98, "passed": true, "blocking": true, "source": "LigandCritic.precheck"}

### 10. critic_correction: complex_integer_charge
- **Choice:** passed: total charge -7.0000, fraction 2.00e-06 *(confidence 0.50)*
- **Why:** LigandCritic precheck
- **Evidence:** {"margin": 0.000998, "passed": true, "blocking": false, "source": "LigandCritic.precheck"}

### 11. critic_correction: minimisation_relaxed
- **Choice:** passed: final GMAX 0.855 kcal/mol/Å (limit 10.0) *(confidence 1.00)*
- **Why:** LigandCritic precheck
- **Evidence:** {"margin": 9.145, "passed": true, "blocking": false, "source": "LigandCritic.precheck"}

### 12. validation: binding mode
- **Choice:** 1/1 published contacts present *(confidence 1.00)*
- **Why:** MET769 at 2.90 Å (hinge backbone NH to quinazoline N1)
- **Evidence:** {"recovered": {"MET769": 2.903}, "missed": [], "extra": ["GLY772"], "source": "minimised model polar contacts, literature Stamos et al. 2002, J Biol Chem 277:46265 (PDB 1M17)"}

### 13. validation: THR766
- **Choice:** THR766 contact absent: True *(confidence 1.00)*
- **Why:** N3 reaches Thr766 only through a crystal water, which this setup removes
- **Evidence:** {"absent": true, "source": "minimised model polar contacts"}

### 14. validation: structure source
- **Choice:** 9D5P at 1.5 Å (best of 6 entries) *(confidence 0.67)*
- **Why:** Q3 ordered by resolution via catalog-STANDIN (DuckDB)
- **Evidence:** {"rows": [{"pdb_id": "9D5P", "resolution": 1.5, "title": "Crystal structure of the ILK/alpha-parvin core complex bound to erlotinib"}, {"pdb_id": "4I22", "resolution": 1.71, "title": "Structure of the monomeric (V948R)gefitinib/erlotinib resistant double mutant (L858R+T790M) EGFR kinase domain co-crystallized with gefitinib"}, {"pdb_id": "1M17", "resolution": 2.6, "title": "Epidermal Growth Factor Receptor tyrosine kinase domain with 4-anilinoquinazoline inhibitor erlotinib"}, {"pdb_id": "4HJO", "resolution": 2.75, "title": "Crystal structure of the inactive EGFR tyrosine kinase domain with erlotinib"}, {"pdb_id": "6DWN", "resolution": 3.0, "title": "Structure of Human Cytochrome P450 1A1 with Erlotinib"}], "sql": "SELECT pdb_id, resolution, title FROM rcsb_entries WHERE system = 'egfr_erlotinib' ORDER BY resolution ASC", "source": "catalog-STANDIN (DuckDB)"}

## Trace
`logs/trace-20261022-190649-7cc564.jsonl`

## Limitations
- PM6 single point of the whole ligand in implicit solvent (igb=5); crystal waters removed; no free-energy barrier.
- His states near the ligand cation are geometric calls; the charged state should be run as a sensitivity check.
- Catalog is a local stand-in unless an adapter with real tables was supplied.
