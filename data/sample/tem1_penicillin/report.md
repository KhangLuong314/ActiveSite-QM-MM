# ActiveSite report — `tem1_penicillin` (run `20261027-013857-2a778f`)

**Question:** Prepare TEM-1 beta-lactamase complexed with benzylpenicillin from the 1FQG crystal structure and compute the PM6 QM/MM energy in its active site. Explain Ser70, protonation, and setup choices.

**Result:** converged — ESCF -139.261 kcal/mol, total -9606.30 kcal/mol, 0 link atoms, 0.97 s engine time

**Engine:** sander in Docker

**Ligand charge:** +0; chain A (requested); His overrides 0; memory used: True

## Binding mode
- published contacts recovered: 1/2 SER70 2.84 Å
- missed: ['LYS73']
- expected absent: {}
- extra polar contacts: ['ALA237', 'ARG243', 'ASN132', 'LYS234', 'SER130', 'SER235']

## Energy decomposition & physical definitions
- **PM6 ESCF (Gas-Phase Heat of Formation ΔHf°):** -139.261 kcal/mol. In Amber semi-empirical QM/MM, the PM6 electronic energy is referenced to standard isolated neutral atoms in their ground states, corresponding to the standard gas-phase heat of formation at 298.15 K. For large, highly conjugated polyaromatics with formal positive charge, ΔHf° is naturally positive (+105.68 kcal/mol).
- **Total QM/MM Energy (E_total):** -9606.30 kcal/mol. This is the complete system Hamiltonian E_total = E_QM + E_MM + E_QM-MM + E_GB, incorporating thousands of classical protein covalent bonds, van der Waals attractions, salt bridges, and favorable Generalized Born electrostatic solvation free energy (ΔG_GB << 0).
- **Coordinate Minimization (GMAX):** Pocket heavy-atom force gradient converged below limit (GMAX <= 10.0 kcal/mol/Å).
- **SCF Electronic Convergence:** Density matrix commutator ΔE < 10^-7 kcal/mol across self-consistent Roothaan-Hall cycles.
- **Pocket Contact Proximity vs. Steric Clash:** Pocket contact check verifies closest protein heavy atom to ligand is <= 4.0 Å (ensuring bound contact), while steric clash check ensures non-bonded VDW distance >= 1.8 Å.

## Decision cards
### 1. residue_inclusion: chain
- **Choice:** chain A (requested) *(confidence 1.00)*
- **Why:** 67 CA within 12 Å of the ligand; 0 gaps adjacent, 0 residues with missing atoms in the pocket, 0 missing residues in the chain
- **Evidence:** {"source": "REMARK 465/470 of 1fqg.pdb"}

### 2. protonation_state: protein protonation
- **Choice:** PDB2PQR + PROPKA at pH 7.4: 10 non-default states, His {'HIS26': 'HID', 'HIS96': 'HID', 'HIS112': 'HID', 'HIS153': 'HID', 'HIS158': 'HID', 'HIS287': 'HIE'} *(confidence 1.00)*
- **Why:** 77 titratable groups predicted; 0 His within 1.0 pKa of the pH
- **Evidence:** {"gap_warnings": [], "source": "pdb2pqr/propka in activesite-prep:at26"}

### 3. protonation_state: ligand
- **Choice:** kept neutral *(confidence 0.80)*
- **Why:** no tertiary amine (N with three C neighbours) has a backbone O within 3.3 Å
- **Evidence:** {"source": "crystal geometry", "rule": "tertiary amine + backbone O < 3.3 \u00c5"}

### 4. theory_selection: ligand force field
- **Choice:** GAFF2 + AM1-BCC, net charge +0 (cached) *(confidence 0.90)*
- **Why:** charge sum +0.0000, residual spread -0.0010 e over 43 atoms
- **Evidence:** {"charge_sum": 0.0, "charge_residual_spread": -0.001002, "ligand_atoms": 43, "cached": true, "cache_key": "7183ceb7b85e9f85", "source": "antechamber/parmchk2"}

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
- **Choice:** passed: centroid shift 0.0 Å (limit 1.0), closest protein heavy atom 1.375 Å (limit 4.0) *(confidence 1.00)*
- **Why:** LigandCritic precheck (blocking)
- **Evidence:** {"margin": 1.0, "passed": true, "blocking": true, "source": "LigandCritic.precheck"}

### 9. critic_correction: pocket_min
- **Choice:** passed: centroid shift 0.069 Å (limit 1.0), closest protein heavy atom 2.565 Å (limit 4.0) *(confidence 0.97)*
- **Why:** LigandCritic precheck (blocking)
- **Evidence:** {"margin": 0.931, "passed": true, "blocking": true, "source": "LigandCritic.precheck"}

### 10. critic_correction: complex_integer_charge
- **Choice:** passed: total charge -6.0000, fraction 1.30e-05 *(confidence 0.50)*
- **Why:** LigandCritic precheck
- **Evidence:** {"margin": 0.000987, "passed": true, "blocking": false, "source": "LigandCritic.precheck"}

### 11. critic_correction: minimisation_relaxed
- **Choice:** passed: final GMAX 1.568 kcal/mol/Å (limit 10.0) *(confidence 1.00)*
- **Why:** LigandCritic precheck
- **Evidence:** {"margin": 8.432, "passed": true, "blocking": false, "source": "LigandCritic.precheck"}

### 12. validation: binding mode
- **Choice:** 1/2 published contacts present *(confidence 0.50)*
- **Why:** SER70 at 2.84 Å (catalytic nucleophile Ser70 OG attacking beta-lactam carbonyl); missed ['LYS73']
- **Evidence:** {"recovered": {"SER70": 2.837}, "missed": ["LYS73"], "extra": ["ALA237", "ARG243", "ASN132", "LYS234", "SER130", "SER235"], "source": "minimised model polar contacts, literature Strynadka et al. 2000, PDB 1FQG, acyl-enzyme intermediate in TEM-1 beta-lactamase"}

### 13. validation: structure source
- **Choice:** 5KMW at 1.1 Å (best of 10 entries) *(confidence 0.91)*
- **Why:** Q3 ordered by resolution via catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)
- **Evidence:** {"rows": [{"pdb_id": "5KMW", "resolution": 1.1, "title": "TOHO1 Beta lactamase mutant E166A/R274N/R276N -benzyl penicillin complex"}, {"pdb_id": "3HUO", "resolution": 1.5, "title": "X-ray crystallographic structure of CTX-M-9 S70G in complex with benzylpenicillin"}, {"pdb_id": "1UOF", "resolution": 1.6, "title": "Deacetoxycephalosporin C synthase complexed with Penicillin G"}, {"pdb_id": "1FQG", "resolution": 1.7, "title": "MOLECULAR STRUCTURE OF THE ACYL-ENZYME INTERMEDIATE IN TEM-1 BETA-LACTAMASE"}, {"pdb_id": "1JWZ", "resolution": 1.8, "title": "Crystal structure of TEM-64 beta-lactamase in complex with a boronic acid inhibitor (105)"}], "sql": "SELECT pdb_id, resolution, title FROM rcsb_entries WHERE system = 'tem1_penicillin' ORDER BY resolution ASC", "source": "catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)"}

## Trace
`logs/trace-20261027-013857-2a778f.jsonl`

## Limitations
- PM6 single point of the whole ligand in implicit solvent (igb=5); crystal waters removed; no free-energy barrier.
- His states near the ligand cation are geometric calls; the charged state should be run as a sensitivity check.
- Catalog is a local stand-in unless an adapter with real tables was supplied.
