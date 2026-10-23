# ActiveSite report — `ippoi_site_b` (run `20261022-191304-0905ca`)

**Question:** Set up a QM/MM model for DNA phosphodiester cleavage at I-PpoI active site B (Mg :372) and compute its PM6 QM/MM energy on the production frame. Explain every setup choice.

**Result:** converged — ESCF -511.364 kcal/mol, total -302070.00 kcal/mol, 4 link atoms, 2.05 s engine time

**Engine:** sander in Docker

**qmcharge:** +1 by MM partial-charge sum (Critic fix after odd-electron failure); retries 1; memory used: False

## Expert agreement
- atom Jaccard vs expert mask: 0.36879432624113473
- only ours: ['WAT17553@H1', 'WAT17553@H2', 'WAT17553@O', 'WAT18332@H1', 'WAT18332@H2', 'WAT18332@O', 'WAT402@H1', 'WAT402@H2', 'WAT402@O', 'WAT403@H1', 'WAT403@H2', 'WAT403@O', 'WAT404@H1', 'WAT404@H2', 'WAT404@O']
- only expert: ['ASN160@C', 'ASN160@CA', 'ASN160@H', 'ASN160@HA', 'ASN160@N', 'ASN160@O', "DA34@C5'", "DA34@H5'", "DA34@H5''", "DA34@O5'", 'DA34@OP1', 'DA34@OP2', 'DA34@P', "DG35@C1'", 'DG35@C2', "DG35@C2'", "DG35@C3'", 'DG35@C4', "DG35@C4'", 'DG35@C5', 'DG35@C6', 'DG35@C8', 'DG35@H1', "DG35@H1'", "DG35@H2'", "DG35@H2''", 'DG35@H21', 'DG35@H22', "DG35@H3'", "DG35@H4'", 'DG35@H8', 'DG35@N1', 'DG35@N2', 'DG35@N3', 'DG35@N7', 'DG35@N9', "DG35@O3'", "DG35@O4'", 'DG35@O6', 'HIE119@C', 'HIE119@CA', 'HIE119@CB', 'HIE119@CD2', 'HIE119@CE1', 'HIE119@CG', 'HIE119@H', 'HIE119@HA', 'HIE119@HB2', 'HIE119@HB3', 'HIE119@HD2', 'HIE119@HE1', 'HIE119@HE2', 'HIE119@N', 'HIE119@ND1', 'HIE119@NE2', 'HIE119@O', 'HIE139@C', 'HIE139@CA', 'HIE139@H', 'HIE139@HA', 'HIE139@N', 'HIE139@O', 'WAT441@H1', 'WAT441@H2', 'WAT441@O', 'WAT473@H1', 'WAT473@H2', 'WAT473@O', 'WAT491@H1', 'WAT491@H2', 'WAT491@O', 'WAT496@H1', 'WAT496@H2', 'WAT496@O']
- expert qmcharge: None (match: None)

## Decision cards
### 1. residue_inclusion: MG372
- **Choice:** MG372 in QM as metal *(confidence 1.00)*
- **Why:** named in the request
- **Evidence:** {"resid": 372, "atomic_number": 12, "mm_charge": 2.0, "source": "geometry of prod00.ncrst (rule 1)"}

### 2. residue_inclusion: DG35
- **Choice:** DG35 in QM as first shell *(confidence 0.85)*
- **Why:** coordinating nucleic-acid atoms; atoms assigned by the scissile-phosphate cut level
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"OP1_dist": 2.035, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 3. residue_inclusion: WAT404
- **Choice:** WAT404 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.08, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 4. residue_inclusion: WAT18332
- **Choice:** WAT18332 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.15, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 5. residue_inclusion: ASN160
- **Choice:** ASN160 in QM as first shell *(confidence 0.85)*
- **Why:** side chain of a protein residue coordinating the metal (cut CA-CB)
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"OD1_dist": 2.152, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 6. residue_inclusion: WAT403
- **Choice:** WAT403 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.159, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 7. residue_inclusion: WAT402
- **Choice:** WAT402 in QM as first shell *(confidence 0.84)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.172, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 8. residue_inclusion: DG35
- **Choice:** DG35 in QM as scissile phosphate *(confidence 1.00)*
- **Why:** P nearest the metal
- **Rejected:**
  - Another phosphate: farther from the metal
- **Evidence:** {"metal_P_dist": 3.405, "P_O3prime_dist": 1.56, "other_P_within_8A": [["DA36@P", 7.451]], "source": "geometry of prod00.ncrst (rule 3)"}

### 9. residue_inclusion: DA34
- **Choice:** DA34 in QM as leaving group *(confidence 0.99)*
- **Why:** residue donating the O3' bonded to the scissile P
- **Evidence:** {"metal_O3prime_dist": 4.107, "P_O3prime_dist": 1.56, "source": "geometry of prod00.ncrst (rule 3)"}

### 10. residue_inclusion: WAT17553
- **Choice:** WAT17553 in QM as nucleophile *(confidence 0.76)*
- **Why:** water O within 4.0 Å of P with the largest O(w)-P-O3' angle (in-line attack)
- **Rejected:**
  - Another water near P: smaller O(w)-P-O3' angle, not in line for attack
- **Evidence:** {"Ow_P_O3prime_angle": 175.1, "Ow_P_dist": 3.93, "search_radius": 4.0, "rejected": [["WAT17462@O", 97.2, 3.518], ["WAT403@O", 73.9, 3.829]], "source": "geometry of prod00.ncrst (rule 4)"}

### 11. residue_inclusion: HIE139
- **Choice:** HIE139 in QM as general base *(confidence 0.60)*
- **Why:** His ring N nearest the nucleophile O within 6.0 Å (side chain, cut CA-CB)
- **Rejected:**
  - No general base: the nucleophile needs a proton acceptor within hydrogen-bond range
- **Evidence:** {"N_Ow_dist": 4.012, "atom": "ND1", "search_radius": 6.0, "rejected": [["HIE139@NE2", 4.526], ["HIE119@ND1", 4.964]], "source": "geometry of prod00.ncrst (rule 5)"}

### 12. cut_level: QM/MM boundary
- **Choice:** cut level 'sugar' (4 link atoms) *(confidence 0.84)*
- **Why:** minimal rejected: ring bonds cut: DA34@C3'-C2', DA34@C3'-C4'; sugar accepted: charge fraction 0.032 <= 0.10, no ring bonds cut, 4 link atoms
- **Rejected:**
  - minimal: ring bonds cut: DA34@C3'-C2', DA34@C3'-C4'
- **Evidence:** {"mask": "@1052-1083,2811-2821,3142-3149,6230,6270-6278,57723-57725,60060-60062", "mm_sum": 1.0318, "fraction": 0.0318, "link_atoms": 4, "source": "geometry of prod00.ncrst"}

### 13. charge_and_spin: qmcharge
- **Choice:** qmcharge +1 (spin 1) *(confidence 0.68)*
- **Why:** MM partial-charge sum (Critic fix after odd-electron failure). First attempt rejected: sander reported an odd electron count (211) at qmcharge +0. The mask cuts nucleotides at the phosphate (sugar level), so whole-residue formal charges (+0) do not apply; the MM partial-charge sum over the QM atoms is +1.032 e, nearest integer +1 (fraction 0.032).
- **Rejected:**
  - qmcharge +0 by formal charges of the residues touched (textbook default): attempt 0: QMMM: System specified with odd number of electrons (  211); QMMM: but odd spin (  1). You most likely have the charge of; QMMM: QM region (qmcharge) set incorrectly. Correct error and re-run calculation.
- **Evidence:** {"mm_partial_sum": 1.0318, "nearest_int": 1, "formal_sum": 0, "per_residue_formal": {"DA34": -1, "DG35": -1, "HIE139": 0, "ASN160": 0, "MG372": 2, "WAT402": 0, "WAT403": 0, "WAT404": 0, "WAT17553": 0, "WAT18332": 0}, "attempts": [{"attempt": 0, "charge": 0, "ok": false, "odd_electrons": 211}, {"attempt": 1, "charge": 1, "ok": true, "odd_electrons": null}], "memory_id": "mem_71b1c050fd", "source": "sander validation + H-MEM"}

### 14. theory_selection: level of theory
- **Choice:** PM6 semi-empirical single point (PME, spin 1) *(confidence 1.00)*
- **Why:** 100% of QM atoms have PM6 parameters; the expert protocol uses PM6 as its low-level method
- **Rejected:**
  - DFT (B3LYP/6-31G*) via QMHub: hours per point; outside the judge CPU budget
  - Pure MM: fixed charges cannot describe the in-line attack
- **Evidence:** {"qm_atoms": 67, "parameterised_fraction": 1.0, "source": "qmhub.ini low level"}

### 15. critic_correction: qm_residues_near_metal
- **Choice:** passed: farthest QM residue nearest-atom distance 4.36 Å (limit 8.0) *(confidence 0.73)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 3.638, "passed": true, "source": "Critic.precheck"}

### 16. critic_correction: first_shell_in_qm
- **Choice:** passed: 6 heavy atoms within 2.8 Å of the metal, 6 in QM *(confidence 1.00)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 1.0, "passed": true, "source": "Critic.precheck"}

### 17. critic_correction: boundary_fraction
- **Choice:** passed: |MM sum - nearest integer| = 0.032 e (limit 0.1) *(confidence 0.53)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 0.0682, "passed": true, "source": "Critic.precheck"}

### 18. critic_correction: expert_mask_provenance
- **Choice:** flagged: expert residue list checked against this topology; flagged ['HIE119: 8.4 Å from the metal', '139: expert says GLN, topology has HIE', 'WAT496: 58.0 Å from the metal', 'WAT473: 56.5 Å from the metal', 'WAT491: 36.7 Å from the metal', 'WAT441: 74.4 Å from the metal'] *(confidence 0.00)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 0.4, "passed": false, "source": "Critic.precheck"}

### 19. validation: expert agreement
- **Choice:** atom Jaccard 0.36879432624113473 *(confidence 0.37)*
- **Why:** comparison with the laboratory record for this site
- **Evidence:** {"expert_mask_present": true, "expert_qmcharge": null, "jaccard": 0.36879432624113473, "only_ours": ["WAT17553@H1", "WAT17553@H2", "WAT17553@O", "WAT18332@H1", "WAT18332@H2", "WAT18332@O", "WAT402@H1", "WAT402@H2", "WAT402@O", "WAT403@H1", "WAT403@H2", "WAT403@O", "WAT404@H1", "WAT404@H2", "WAT404@O"], "only_expert": ["ASN160@C", "ASN160@CA", "ASN160@H", "ASN160@HA", "ASN160@N", "ASN160@O", "DA34@C5'", "DA34@H5'", "DA34@H5''", "DA34@O5'", "DA34@OP1", "DA34@OP2", "DA34@P", "DG35@C1'", "DG35@C2", "DG35@C2'", "DG35@C3'", "DG35@C4", "DG35@C4'", "DG35@C5", "DG35@C6", "DG35@C8", "DG35@H1", "DG35@H1'", "DG35@H2'", "DG35@H2''", "DG35@H21", "DG35@H22", "DG35@H3'", "DG35@H4'", "DG35@H8", "DG35@N1", "DG35@N2", "DG35@N3", "DG35@N7", "DG35@N9", "DG35@O3'", "DG35@O4'", "DG35@O6", "HIE119@C", "HIE119@CA", "HIE119@CB", "HIE119@CD2", "HIE119@CE1", "HIE119@CG", "HIE119@H", "HIE119@HA", "HIE119@HB2", "HIE1

## Trace
`logs/trace-20261022-191304-0905ca.jsonl`

## Limitations
- PM6 single point only; no free-energy barrier computed locally.
- Catalog is a local stand-in unless an adapter with real tables was supplied.
