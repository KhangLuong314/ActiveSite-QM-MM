# ActiveSite report — `ippoi_site_a` (run `20261022-190635-dae15a`)

**Question:** Set up a QM/MM model for DNA phosphodiester cleavage at I-PpoI active site A (Mg :371) and compute its PM6 QM/MM energy on the production frame. Explain every setup choice.

**Result:** converged — ESCF -456.563 kcal/mol, total -302060.00 kcal/mol, 4 link atoms, 2.62 s engine time

**Engine:** sander in Docker

**qmcharge:** +1 by MM partial-charge sum (Critic fix after odd-electron failure); retries 1; memory used: False

## Expert agreement
- atom Jaccard vs expert mask: 1.0
- only ours: []
- only expert: []
- expert qmcharge: 1 (match: True)

## Decision cards
### 1. residue_inclusion: MG371
- **Choice:** MG371 in QM as metal *(confidence 1.00)*
- **Why:** named in the request
- **Evidence:** {"resid": 371, "atomic_number": 12, "mm_charge": 2.0, "source": "geometry of prod00.ncrst (rule 1)"}

### 2. residue_inclusion: DG14
- **Choice:** DG14 in QM as first shell *(confidence 0.86)*
- **Why:** coordinating nucleic-acid atoms; atoms assigned by the scissile-phosphate cut level
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"OP2_dist": 2.013, "P_dist": 2.76, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 3. residue_inclusion: WAT399
- **Choice:** WAT399 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.061, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 4. residue_inclusion: ASN322
- **Choice:** ASN322 in QM as first shell *(confidence 0.85)*
- **Why:** side chain of a protein residue coordinating the metal (cut CA-CB)
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"OD1_dist": 2.097, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 5. residue_inclusion: WAT398
- **Choice:** WAT398 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.098, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 6. residue_inclusion: DA13
- **Choice:** DA13 in QM as first shell *(confidence 0.85)*
- **Why:** coordinating nucleic-acid atoms; atoms assigned by the scissile-phosphate cut level
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O3'_dist": 2.117, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 7. residue_inclusion: WAT400
- **Choice:** WAT400 in QM as first shell *(confidence 0.85)*
- **Why:** whole water within FIRST_SHELL of the metal
- **Rejected:**
  - Leave it in MM: a ligand inside the first shell polarises the metal; point charges cannot describe it
- **Evidence:** {"O_dist": 2.146, "cutoff": 2.8, "source": "geometry of prod00.ncrst (rule 2)"}

### 8. residue_inclusion: DG14
- **Choice:** DG14 in QM as scissile phosphate *(confidence 0.98)*
- **Why:** P nearest the metal
- **Rejected:**
  - Another phosphate: farther from the metal
- **Evidence:** {"metal_P_dist": 2.76, "P_O3prime_dist": 1.646, "other_P_within_8A": [["DA13@P", 6.441]], "source": "geometry of prod00.ncrst (rule 3)"}

### 9. residue_inclusion: DA13
- **Choice:** DA13 in QM as leaving group *(confidence 1.00)*
- **Why:** residue donating the O3' bonded to the scissile P
- **Evidence:** {"metal_O3prime_dist": 2.117, "P_O3prime_dist": 1.646, "source": "geometry of prod00.ncrst (rule 3)"}

### 10. residue_inclusion: WAT397
- **Choice:** WAT397 in QM as nucleophile *(confidence 0.74)*
- **Why:** water O within 4.0 Å of P with the largest O(w)-P-O3' angle (in-line attack)
- **Rejected:**
  - Another water near P: smaller O(w)-P-O3' angle, not in line for attack
- **Evidence:** {"Ow_P_O3prime_angle": 171.9, "Ow_P_dist": 3.569, "search_radius": 4.0, "rejected": [["WAT12049@O", 101.2, 3.563], ["WAT609@O", 79.2, 3.647], ["WAT400@O", 59.2, 3.373]], "source": "geometry of prod00.ncrst (rule 4)"}

### 11. residue_inclusion: HIE301
- **Choice:** HIE301 in QM as general base *(confidence 0.66)*
- **Why:** His ring N nearest the nucleophile O within 6.0 Å (side chain, cut CA-CB)
- **Rejected:**
  - No general base: the nucleophile needs a proton acceptor within hydrogen-bond range
- **Evidence:** {"N_Ow_dist": 2.782, "atom": "ND1", "search_radius": 6.0, "rejected": [["HIE301@NE2", 4.192], ["HIE281@ND1", 4.319], ["HIE281@NE2", 5.451]], "source": "geometry of prod00.ncrst (rule 5)"}

### 12. cut_level: QM/MM boundary
- **Choice:** cut level 'sugar' (4 link atoms) *(confidence 0.84)*
- **Why:** minimal rejected: ring bonds cut: DA13@C3'-C2', DA13@C3'-C4'; sugar accepted: charge fraction 0.032 <= 0.10, no ring bonds cut, 4 link atoms
- **Rejected:**
  - minimal: ring bonds cut: DA13@C3'-C2', DA13@C3'-C4'
- **Evidence:** {"mask": "@385-416,5256-5266,5587-5594,6229,6255-6266", "mm_sum": 1.0318, "fraction": 0.0318, "link_atoms": 4, "source": "geometry of prod00.ncrst"}

### 13. charge_and_spin: qmcharge
- **Choice:** qmcharge +1 (spin 1) *(confidence 0.68)*
- **Why:** MM partial-charge sum (Critic fix after odd-electron failure). First attempt rejected: sander reported an odd electron count (203) at qmcharge +0. The mask cuts nucleotides at the phosphate (sugar level), so whole-residue formal charges (+0) do not apply; the MM partial-charge sum over the QM atoms is +1.032 e, nearest integer +1 (fraction 0.032).
- **Rejected:**
  - qmcharge +0 by formal charges of the residues touched (textbook default): attempt 0: QMMM: System specified with odd number of electrons (  203); QMMM: but odd spin (  1). You most likely have the charge of; QMMM: QM region (qmcharge) set incorrectly. Correct error and re-run calculation.
- **Evidence:** {"mm_partial_sum": 1.0318, "nearest_int": 1, "formal_sum": 0, "per_residue_formal": {"DA13": -1, "DG14": -1, "HIE301": 0, "ASN322": 0, "MG371": 2, "WAT397": 0, "WAT398": 0, "WAT399": 0, "WAT400": 0}, "attempts": [{"attempt": 0, "charge": 0, "ok": false, "odd_electrons": 203}, {"attempt": 1, "charge": 1, "ok": true, "odd_electrons": null}], "memory_id": "mem_3acc0f3315", "source": "sander validation + H-MEM"}

### 14. theory_selection: level of theory
- **Choice:** PM6 semi-empirical single point (PME, spin 1) *(confidence 1.00)*
- **Why:** 100% of QM atoms have PM6 parameters; the expert protocol uses PM6 as its low-level method
- **Rejected:**
  - DFT (B3LYP/6-31G*) via QMHub: hours per point; outside the judge CPU budget
  - Pure MM: fixed charges cannot describe the in-line attack
- **Evidence:** {"qm_atoms": 64, "parameterised_fraction": 1.0, "source": "qmhub.ini low level"}

### 15. critic_correction: qm_residues_near_metal
- **Choice:** passed: farthest QM residue nearest-atom distance 5.04 Å (limit 8.0) *(confidence 0.69)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 2.958, "passed": true, "source": "Critic.precheck"}

### 16. critic_correction: first_shell_in_qm
- **Choice:** passed: 7 heavy atoms within 2.8 Å of the metal, 7 in QM *(confidence 1.00)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 1.0, "passed": true, "source": "Critic.precheck"}

### 17. critic_correction: boundary_fraction
- **Choice:** passed: |MM sum - nearest integer| = 0.032 e (limit 0.1) *(confidence 0.53)*
- **Why:** Critic precheck on the proposed region
- **Evidence:** {"margin": 0.0682, "passed": true, "source": "Critic.precheck"}

### 18. validation: expert agreement
- **Choice:** atom Jaccard 1.0 *(confidence 1.00)*
- **Why:** comparison with the laboratory record for this site
- **Evidence:** {"expert_mask_present": true, "expert_qmcharge": 1, "jaccard": 1.0, "only_ours": [], "only_expert": [], "expert_atoms": 64, "charge_match": true, "source": "catalog-STANDIN (DuckDB)"}

## Trace
`logs/trace-20261022-190635-dae15a.jsonl`

## Limitations
- PM6 single point only; no free-energy barrier computed locally.
- Catalog is a local stand-in unless an adapter with real tables was supplied.
